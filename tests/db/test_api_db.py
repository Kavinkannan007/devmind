"""Opt-in SQL-backed API checks. Start the disposable server in verify.mjs first."""

import json
import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest

from backend import indexer, main
from backend.auth import user
from backend.db import database, rows

DSN = os.getenv("DEVMIND_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DSN, reason="Set DEVMIND_TEST_DATABASE_URL to a disposable local DB"
)


@pytest.mark.asyncio
async def test_two_users_index_retrieve_chat_and_quota(monkeypatch):
    assert urlparse(DSN).hostname in {"localhost", "127.0.0.1", "::1"}
    monkeypatch.setenv("DATABASE_URL", DSN)
    monkeypatch.setenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    monkeypatch.setenv("QUESTIONS_PER_DAY", "3")
    owner, outsider = uuid4(), uuid4()
    sha = "a" * 40
    source = "def format_title():\n    return 'DevMind'\n"
    inputs = {"labels.py": source, "api.py": "from . import labels\n"}

    async def snapshot(url, **kwargs):
        return {
            "metadata": {"sha": sha},
            "unchanged": False,
            "files": [{"path": p, "source": s, "language": "Python"} for p, s in inputs.items()],
            "discovered": len(inputs),
            "truncated": False,
            "skipped": [],
        }

    class FixtureModels:
        async def embed_content(self, *, contents, **kwargs):
            # Orthogonal unit vectors intentionally favor the other file for a search.
            vectors = []
            for content in contents:
                text = content.parts[0].text
                axis = 0 if "from ." in text or text == "format_title" else 1
                values = [0.0] * 768
                values[axis] = 1.0
                vectors.append(SimpleNamespace(values=values))
            return SimpleNamespace(embeddings=vectors)

        async def generate_content(self, **kwargs):
            payload = json.loads(kwargs["contents"])
            assert any(item["path"] == "labels.py" for item in payload["evidence"])
            return SimpleNamespace(
                text=json.dumps({"answer": "A source excerpt [S1].", "sources": [1]})
            )

    @asynccontextmanager
    async def fake_provider():
        yield SimpleNamespace(models=FixtureModels())

    monkeypatch.setattr(indexer, "ingest", snapshot)
    monkeypatch.setattr(indexer, "provider", fake_provider)
    monkeypatch.setattr(main, "provider", fake_provider)
    async with database() as db:
        await db.execute("insert into auth.users (id) values (%s),(%s)", (owner, outsider))
    previous = main.app.dependency_overrides.copy()
    try:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://devmind.test") as client:
            assert (await client.get("/repos")).status_code == 401
            main.app.dependency_overrides[user] = lambda: owner
            payload = {"url": "https://github.com/devmind/test-fixture"}
            first = await client.post("/repos", json=payload)
            assert first.status_code == 202, first.text
            rid = first.json()["id"]
            assert (await client.post("/repos", json=payload)).json()["id"] == rid
            base = f"/repos/{rid}"
            async with database() as db:
                jobs = await rows(
                    db,
                    """select j.id,j.repo_id,r.url,r.sha,r.embedding_model
                    from jobs j join repositories r on r.id=j.repo_id where r.id=%s""",
                    (rid,),
                )
                assert len(jobs) == 1
                assert (
                    await rows(
                        db, "select used from usage where owner_id=%s and kind='import'", (owner,)
                    )
                )[0]["used"] == 1
            await indexer.index(jobs[0])
            workspace = await client.get(base)
            assert workspace.status_code == 200, workspace.text
            job = workspace.json()["job"]
            assert job["status"] == "ready"
            assert job["done"] == job["total"] > 0
            assert (await client.get(base + "/file", params={"path": "labels.py"})).json()[
                "text"
            ] == source
            impact = await client.get(base + "/impact", params={"path": "labels.py"})
            assert impact.json()["dependants"] == {"api.py": 1}

            question = {"question": "format_title"}
            found = await client.post(base + "/search", json=question)
            assert found.status_code == 200, found.text
            # Lexical evidence lifts this symbol above a better vector-only match.
            assert found.json()[0]["path"] == "labels.py"
            answer = await client.post(base + "/ask", json=question)
            assert answer.status_code == 200, answer.text
            citation = answer.json()["citations"][0]
            assert citation["url"].endswith(f"/blob/{sha}/labels.py#L1-L2")
            assert citation["text"] == source
            assert (await client.post(base + "/documents", json=question)).status_code == 200
            assert (await client.post(base + "/ask", json=question)).status_code == 429

            main.app.dependency_overrides[user] = lambda: outsider
            assert (await client.get("/repos")).json() == []
            for endpoint in [
                base,
                base + "/file?path=labels.py",
                base + "/history",
                base + "/documents",
                base + "/impact?path=labels.py",
            ]:
                assert (await client.get(endpoint)).status_code == 404
            for endpoint in ["/ask", "/documents", "/search", "/refresh"]:
                assert (await client.post(base + endpoint, json=question)).status_code == 404
            assert (await client.delete(base)).status_code == 404
            main.app.dependency_overrides[user] = lambda: owner

        async with httpx.AsyncClient(
            transport=transport, base_url="http://devmind.test"
        ) as refreshed:
            assert (await refreshed.get(base + "/history")).json()[0]["citations"] == [citation]
            assert len((await refreshed.get(base + "/documents")).json()) == 1
            assert (await refreshed.delete(base)).status_code == 200
            assert (await refreshed.get("/repos")).json() == []
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(previous)
        async with database() as db:
            await db.execute("delete from auth.users where id in (%s,%s)", (owner, outsider))
