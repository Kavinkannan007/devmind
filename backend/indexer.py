"""A bounded worker per slot. Transaction-scoped advisory locks recover on disconnect."""

import asyncio
import logging
from collections import Counter

from fastapi import HTTPException
from google.genai.errors import APIError
from psycopg.types.json import Jsonb

from .ai import embedding_model, embeddings, provider
from .analysis import analyze, chunks, resolve_import
from .config import limit, setting
from .db import database, rows
from .github import GitHubError, ingest

log = logging.getLogger("devmind.indexer")


async def index(job):
    jid, rid = job["id"], job["repo_id"]

    async def progress(stage, done=0, total=0):
        async with database() as db:
            await db.execute(
                "update jobs set status='running',stage=%s,done=%s,total=%s where id=%s",
                (stage, done, total, jid),
            )

    snapshot = await ingest(
        job["url"],
        token=setting("GITHUB_TOKEN"),
        max_files=limit("MAX_FILES", 300, 1000),
        max_file_bytes=limit("MAX_FILE_BYTES", 204800, 500000),
        max_bytes=limit("MAX_BYTES", 5242880, 10000000),
        on_progress=progress,
        known_sha=job["sha"] if job["embedding_model"] == embedding_model() else None,
        timeout=limit("INDEX_TIMEOUT", 600, 3600),
    )
    meta = snapshot["metadata"]
    if snapshot["unchanged"]:
        async with database() as db:
            await db.execute(
                "update repositories set metadata=metadata || %s,updated_at=now() where id=%s",
                (Jsonb(meta), rid),
            )
            await db.execute(
                "update jobs set status='ready',stage='Ready' where id=%s", (jid,)
            )
        return
    files = snapshot["files"]
    paths = {f["path"] for f in files}
    await progress("Parsing source code", 0, len(files))
    pieces, syms, edges, file_rows = [], [], set(), []
    frameworks = set()
    known_frameworks = {
        "react",
        "vue",
        "django",
        "fastapi",
        "flask",
        "next",
        "express",
        "svelte",
        "angular",
    }
    for i, f in enumerate(files, 1):
        p, t = f["path"], f["source"]
        parsed = analyze(p, t)
        parsed["language"] = f["language"]
        pieces.extend(
            chunks(
                rid,
                meta["sha"],
                p,
                t,
                parsed,
                max_chars=limit("CHUNK_CHARS", 3200, 6000),
            )
        )
        file_rows.append(
            (rid, p, f["language"], t, len(t.splitlines()), parsed["parsed"])
        )
        for s in parsed["symbols"] + parsed["routes"]:
            syms.append((rid, p, s["name"], s["kind"], s["start_line"], s["end_line"]))
        for s in parsed["imports"]:
            spec = s["specifier"]
            target = resolve_import(p, spec, paths)
            kind = (
                "internal"
                if target
                else ("unresolved" if spec.startswith(".") else "external")
            )
            edges.add((rid, p, target or spec, kind, s["start_line"]))
            framework = spec.split("/")[0].split(".")[0].lower()
            if kind == "external" and framework in known_frameworks:
                frameworks.add(framework)
        if i % 20 == 0:
            await progress("Parsing source code", i, len(files))
    if not pieces:
        raise GitHubError(
            "No eligible source text was available within the configured limits."
        )
    if len(pieces) > limit("MAX_CHUNKS", 3000, 8000):
        raise GitHubError("Chunk limit reached. Import a smaller repository.")
    meta.update(
        discovered=snapshot["discovered"],
        truncated=snapshot["truncated"],
        skipped=dict(Counter(s["reason"] for s in snapshot["skipped"])),
        skipped_files=snapshot["skipped"][:500],
        frameworks=sorted(frameworks),
    )
    await progress("Generating embeddings", 0, len(pieces))
    # Reuse exact source within this owner's previous snapshot and embedding space.
    cache = {}
    if job["embedding_model"] == embedding_model():
        async with database() as db:
            for row in await rows(
                db,
                "select content_hash,embedding::text as vector from chunks where repo_id=%s",
                (rid,),
            ):
                cache[row["content_hash"]] = row["vector"]
    async with provider() as ai:
        for start in range(0, len(pieces), 32):
            batch = pieces[start : start + 32]
            missing = {
                c["content_hash"]: c["text"]
                for c in batch
                if c["content_hash"] not in cache
            }
            if missing:
                cache.update(
                    zip(
                        missing,
                        await embeddings(ai, list(missing.values())),
                        strict=True,
                    )
                )
            await progress("Generating embeddings", start + len(batch), len(pieces))
    await progress("Saving indexed data")
    async with database() as db:
        await db.execute("delete from files where repo_id=%s", (rid,))
        async with db.cursor() as cur:
            await cur.executemany(
                "insert into files values (%s,%s,%s,%s,%s,%s)", file_rows
            )
            await cur.executemany(
                "insert into symbols values (%s,%s,%s,%s,%s,%s)", syms
            )
            await cur.executemany("insert into edges values (%s,%s,%s,%s,%s)", edges)
            await cur.executemany(
                """insert into chunks(id,repo_id,path,sha,language,symbol,start_line,end_line,text,content_hash,embedding)
                                     values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)""",
                (
                    (
                        c["id"],
                        rid,
                        c["path"],
                        meta["sha"],
                        c["language"],
                        c["symbol"],
                        c["start_line"],
                        c["end_line"],
                        c["text"],
                        c["content_hash"],
                        cache[c["content_hash"]],
                    )
                    for c in pieces
                ),
            )
        await db.execute(
            "update repositories set sha=%s,metadata=%s,embedding_model=%s,updated_at=now() where id=%s",
            (meta["sha"], Jsonb(meta), embedding_model(), rid),
        )
        await db.execute(
            "update jobs set status='ready',stage='Ready',done=total where id=%s",
            (jid,),
        )


async def run_one(slot):
    async with database() as lease:
        # Keep a session-pooler connection throughout the import. Locks release on crash.
        if not (
            await rows(lease, "select pg_try_advisory_xact_lock(92751,%s) ok", (slot,))
        )[0]["ok"]:
            return
        jobs = await rows(
            lease,
            """select j.id,j.repo_id,r.url,r.sha,r.embedding_model from jobs j
           join repositories r on r.id=j.repo_id where j.status in ('queued','running') order by j.created_at limit 32""",
        )
        for job in jobs:
            if not (
                await rows(
                    lease,
                    "select pg_try_advisory_xact_lock(hashtextextended(%s,567)) ok",
                    (str(job["id"]),),
                )
            )[0]["ok"]:
                continue
            live = await rows(
                lease, "select status from jobs where id=%s", (job["id"],)
            )
            if not live or live[0]["status"] not in {"queued", "running"}:
                continue
            try:
                async with asyncio.timeout(limit("INDEX_TIMEOUT", 600, 3600)):
                    await index(job)
            except Exception as exc:
                message = "Indexing failed. Check the database connection and retry."
                if isinstance(exc, GitHubError):
                    message = str(exc)
                elif isinstance(exc, HTTPException):
                    message = exc.detail
                elif isinstance(exc, APIError):
                    message = f"Gemini embedding request failed (HTTP {exc.code}). Check model access, key and quota."
                elif isinstance(exc, TimeoutError):
                    message = "Indexing timed out. Try a smaller repository."
                log.warning(
                    "index_failed job=%s category=%s", job["id"], type(exc).__name__
                )
                async with database() as db:
                    await db.execute(
                        "update jobs set status='failed',stage='Failed',error=%s where id=%s",
                        (message, job["id"]),
                    )
            return


async def worker(slot):
    while True:
        if setting("DATABASE_URL"):
            try:
                await run_one(slot)
            except Exception as exc:
                log.warning(
                    "worker_unavailable slot=%s category=%s", slot, type(exc).__name__
                )
        await asyncio.sleep(3)
