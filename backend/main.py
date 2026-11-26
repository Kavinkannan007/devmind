import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

import httpx
import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.genai.errors import APIError
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, field_validator

from .ai import generate, provider, retrieve
from .analysis import impact
from .auth import user
from .config import limit, setting
from .db import charge, database, owned, rows
from .github import GitHubError, normalize_url, redact
from .indexer import worker


@asynccontextmanager
async def lifespan(app):
    tasks = [
        asyncio.create_task(worker(i)) for i in range(limit("CONCURRENT_IMPORTS", 2, 8))
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="DevMind", version="0.1.0", lifespan=lifespan)
origins = [
    u.strip().rstrip("/")
    for u in setting(
        "FRONTEND_URL", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(psycopg.Error)
async def database_failure(request: Request, exc):
    logging.getLogger("devmind").warning(
        "database_error category=%s", type(exc).__name__
    )
    return JSONResponse(
        {
            "detail": "Database unavailable. Check DATABASE_URL and apply the DevMind migration."
        },
        503,
    )


@app.exception_handler(APIError)
async def provider_failure(request: Request, exc):
    return JSONResponse(
        {
            "detail": f"Gemini returned HTTP {exc.code}. Check the configured model, API key and quota."
        },
        429 if exc.code == 429 else 502,
    )


@app.exception_handler(httpx.RequestError)
async def network_failure(request: Request, exc):
    return JSONResponse(
        {"detail": "External service connection failed. Please retry."}, 502
    )


@app.get("/health")
async def health():
    missing = [
        k
        for k in (
            "DATABASE_URL",
            "SUPABASE_URL",
            "SUPABASE_PUBLISHABLE_KEY",
            "GEMINI_API_KEY",
        )
        if not setting(k)
    ]
    return {
        "status": "online",
        "configuration": "incomplete" if missing else "configured",
        "missing": missing,
    }


class ImportRequest(BaseModel):
    url: str = Field(min_length=1, max_length=250)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    path: str | None = Field(default=None, max_length=1024)

    @field_validator("question")
    @classmethod
    def clean(cls, q):
        q = redact(q.strip())
        if not q:
            raise ValueError("Enter a question.")
        return q


async def schedule(db, rid, owner):
    active = await rows(
        db,
        "select id from jobs where repo_id=%s and status in ('queued','running')",
        (rid,),
    )
    if active:
        return
    await charge(db, owner, "import")
    await db.execute(
        "insert into jobs(repo_id,status,stage) values (%s,'queued','Validating repository')",
        (rid,),
    )


@app.post("/repos", status_code=202)
async def create(data: ImportRequest, owner: UUID = Depends(user)):
    try:
        org, name = normalize_url(data.url)
    except GitHubError as exc:
        raise HTTPException(422, str(exc))
    url = f"https://github.com/{org}/{name}"
    async with database() as db:
        await db.execute(
            "insert into workspaces(id) values (%s) on conflict do nothing", (owner,)
        )
        (repo,) = await rows(
            db,
            """insert into repositories(owner_id,url,name) values (%s,%s,%s)
            on conflict(owner_id,url) do update set name=excluded.name returning id,sha""",
            (owner, url, f"{org}/{name}"),
        )
        if not repo["sha"]:
            await schedule(db, repo["id"], owner)
    return {"id": repo["id"]}


@app.get("/repos")
async def repositories(owner: UUID = Depends(user)):
    async with database() as db:
        return await rows(
            db,
            """select r.id,r.name,r.url,r.sha,r.updated_at,j.status from repositories r
           left join lateral (select status from jobs where repo_id=r.id order by created_at desc limit 1) j on true
           where owner_id=%s order by r.updated_at desc""",
            (owner,),
        )


@app.get("/repos/{rid}")
async def workspace(rid: UUID, owner: UUID = Depends(user)):
    async with database() as db:
        await db.execute("set transaction isolation level repeatable read")
        repo = await owned(db, rid, owner)
        repo["job"] = (
            await rows(
                db,
                "select status,stage,done,total,error from jobs where repo_id=%s order by created_at desc limit 1",
                (rid,),
            )
        )[0]
        repo["files"] = await rows(
            db,
            "select path,lines,language,parsed from files where repo_id=%s order by path",
            (rid,),
        )
        repo["edges"] = await rows(
            db,
            "select path as source,target,kind,line from edges where repo_id=%s order by path,line",
            (rid,),
        )
        repo["symbols"] = await rows(
            db,
            "select path,name,kind,start_line,end_line from symbols where repo_id=%s order by path,start_line",
            (rid,),
        )
        return repo


@app.post("/repos/{rid}/refresh", status_code=202)
async def refresh(rid: UUID, owner: UUID = Depends(user)):
    async with database() as db:
        await owned(db, rid, owner, lock=True)
        await schedule(db, rid, owner)
    return {"id": rid}


@app.delete("/repos/{rid}")
async def delete(rid: UUID, owner: UUID = Depends(user)):
    async with database() as db:
        await owned(db, rid, owner, lock=True)
        active = await rows(
            db,
            "select id from jobs where repo_id=%s and status in ('running','queued')",
            (rid,),
        )
        if active:
            raise HTTPException(
                409, "Wait for the import to finish before deleting this repository."
            )
        await db.execute("delete from repositories where id=%s", (rid,))
    return {"deleted": True}


@app.get("/repos/{rid}/file")
async def file(
    rid: UUID, path: str = Query(max_length=1024), owner: UUID = Depends(user)
):
    async with database() as db:
        await owned(db, rid, owner)
        found = await rows(
            db,
            "select path,text,language from files where repo_id=%s and path=%s",
            (rid, path),
        )
        if not found:
            raise HTTPException(404, "File unavailable in this snapshot.")
        return found[0]


@app.get("/repos/{rid}/impact")
async def affected(
    rid: UUID, path: str = Query(max_length=1024), owner: UUID = Depends(user)
):
    async with database() as db:
        await owned(db, rid, owner)
        if not await rows(
            db, "select 1 from files where repo_id=%s and path=%s", (rid, path)
        ):
            raise HTTPException(404, "Select an indexed file.")
        edges = await rows(
            db,
            "select path,target from edges where repo_id=%s and kind='internal'",
            (rid,),
        )
        return impact(path, [(e["path"], e["target"]) for e in edges])


@app.get("/repos/{rid}/{kind}")
async def history(
    rid: UUID, kind: Literal["history", "documents"], owner: UUID = Depends(user)
):
    async with database() as db:
        await owned(db, rid, owner)
        return await rows(
            db,
            "select id,question,answer,citations,created_at from entries where repo_id=%s and kind=%s order by id",
            (rid, "ask" if kind == "history" else kind),
        )


@app.post("/repos/{rid}/{kind}")
async def intelligence(
    rid: UUID,
    kind: Literal["ask", "search", "documents"],
    data: Question,
    owner: UUID = Depends(user),
):
    async with database() as db:
        repo = await owned(db, rid, owner)
        if not repo["sha"]:
            raise HTTPException(
                409, "Wait for a successful index before using repository intelligence."
            )
        if data.path and not await rows(
            db, "select 1 from files where repo_id=%s and path=%s", (rid, data.path)
        ):
            raise HTTPException(404, "File unavailable.")
        await charge(db, owner, "question")
        history = (
            await rows(
                db,
                """select left(question,400) question,left(answer,800) answer from entries
             where repo_id=%s and kind='ask' order by id desc limit 3""",
                (rid,),
            )
            if kind == "ask"
            else []
        )
    retrieval_query = data.question
    if history and len(data.question.split()) < 12:
        retrieval_query += "\n" + history[0]["question"]
    async with provider() as ai:
        snippets = await retrieve(ai, repo, retrieval_query, data.path)
        if kind == "search":
            return snippets
        result = await generate(
            ai, data.question, snippets, list(reversed(history)), kind == "documents"
        )
    async with database() as db:
        await owned(db, rid, owner)
        await db.execute(
            "insert into entries(repo_id,kind,question,answer,citations) values (%s,%s,%s,%s,%s)",
            (rid, kind, data.question, result["answer"], Jsonb(result["citations"])),
        )
    return result
