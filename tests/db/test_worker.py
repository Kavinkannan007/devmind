"""Verify cross-session worker locks on a disposable native PostgreSQL server."""

import asyncio
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from backend import indexer
from backend.db import database, rows
from backend.github import GitHubError

ADMIN = os.getenv("DEVMIND_TEST_NATIVE_DSN")
pytestmark = pytest.mark.skipif(not ADMIN, reason="Requires a disposable native PostgreSQL server")


@pytest.mark.asyncio
async def test_worker_recovers_abandoned_job_and_excludes_competitors(monkeypatch):
    config = conninfo_to_dict(ADMIN)
    host = config.get("host", "")
    assert host.startswith("/") or host in {"127.0.0.1", "localhost", "::1"}
    name = "devmind_worker_test_" + uuid4().hex
    admin = await psycopg.AsyncConnection.connect(ADMIN, autocommit=True)
    async with admin:
        await admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        try:
            monkeypatch.setenv("DATABASE_URL", make_conninfo(ADMIN, dbname=name))
            await verify_locking(monkeypatch)
        finally:
            await admin.execute(sql.SQL("drop database {}").format(sql.Identifier(name)))


async def verify_locking(monkeypatch):
    rid, jid = uuid4(), uuid4()
    async with database() as db:
        await db.execute("create schema devmind")
        # The real scheduler touches only these fields. The full migration is covered in verify.mjs.
        await db.execute("""create table repositories (id uuid primary key,url text,sha text,
                          embedding_model text,metadata jsonb default '{}')""")
        await db.execute("""create table jobs (id uuid primary key,repo_id uuid,status text,stage text,
                          error text,created_at timestamptz default now())""")
        await db.execute("insert into repositories(id) values (%s)", (rid,))
        await db.execute("insert into jobs(id,repo_id,status) values (%s,%s,'queued')", (jid, rid))
    entered = asyncio.Event()
    hold = asyncio.Event()
    attempts = []

    async def interrupted(job):
        attempts.append(job["id"])
        async with database() as db:
            await db.execute("update jobs set status='running' where id=%s", (jid,))
        entered.set()
        await hold.wait()

    monkeypatch.setattr(indexer, "index", interrupted)
    first = asyncio.create_task(indexer.run_one(0))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        await asyncio.wait_for(asyncio.gather(indexer.run_one(0), indexer.run_one(1)), 5)
        assert attempts == [jid]
    finally:
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)

    async def failure(job):
        attempts.append(job["id"])
        raise GitHubError("Provider unavailable during test")

    monkeypatch.setattr(indexer, "index", failure)
    await indexer.run_one(0)
    assert attempts == [jid, jid]
    async with database() as db:
        (result,) = await rows(db, "select status,error from jobs where id=%s", (jid,))
        assert result == {"status": "failed", "error": "Provider unavailable during test"}
