from contextlib import asynccontextmanager

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

from .config import limit, setting


@asynccontextmanager
async def database():
    if not setting("DATABASE_URL"):
        raise HTTPException(503, "Configure DATABASE_URL in backend/.env.")
    conn = await psycopg.AsyncConnection.connect(
        setting("DATABASE_URL"),
        row_factory=dict_row,
        connect_timeout=8,
        prepare_threshold=None,
    )
    async with conn:
        await conn.execute("set local search_path = devmind,extensions,public")
        await conn.execute("set local statement_timeout = '25s'")
        yield conn


async def rows(db, sql, args=()):
    return await (await db.execute(sql, args)).fetchall()


async def owned(db, rid, owner, lock=False):
    found = await rows(
        db,
        "select * from repositories where id=%s and owner_id=%s" + (" for update" if lock else ""),
        (rid, owner),
    )
    if not found:
        raise HTTPException(404, "Repository unavailable.")
    return found[0]


async def charge(db, owner, kind):
    maximum = (
        limit("IMPORTS_PER_DAY", 5, 100)
        if kind == "import"
        else limit("QUESTIONS_PER_DAY", 60, 2000)
    )
    used = await rows(
        db,
        """insert into usage values (%s,(now() at time zone 'UTC')::date,%s,1)
        on conflict(owner_id,day,kind) do update set used=usage.used+1 where usage.used < %s
        returning used""",
        (owner, kind, maximum),
    )
    if not used:
        raise HTTPException(429, "Daily quota reached. Try again after midnight UTC.")

    burst = await rows(
        db,
        """insert into usage values (%s,(now() at time zone 'UTC')::date,
        'minute-' || to_char(now() at time zone 'UTC','HH24MI'),1)
        on conflict(owner_id,day,kind) do update set used=usage.used+1 where usage.used < %s returning used""",
        (owner, limit("OPERATIONS_PER_MINUTE", 10, 100)),
    )
    if not burst:
        raise HTTPException(429, "Too many requests. Try again in a minute.")
