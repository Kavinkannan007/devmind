"""Opt-in live acceptance tests. See docs/live-tests.md for accounts and limits."""

import base64
import json
import os
import re
import time
import unittest
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

import httpx
import psycopg
from dotenv import dotenv_values

CASES = [
    ("pypa/sampleproject", "src/sample/simple.py", "What does add_one return?"),
    (
        "sindresorhus/escape-string-regexp",
        "index.js",
        "How does this library escape regular expression characters?",
    ),
]


def token_subject(token):
    # This local check only catches accidentally supplied credentials for the same user.
    # The running API independently performs authentication with the project's Supabase Auth.
    try:
        payload = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return UUID(data["sub"])
    except (IndexError, KeyError, ValueError):
        raise ValueError(
            "Use access tokens issued for two signed-in Supabase test accounts."
        ) from None


def required(name):
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Set {name} before enabling live acceptance tests.")
    return value


@unittest.skipUnless(
    os.getenv("DEVMIND_LIVE") == "1", "Requires two live Supabase accounts and enabled Gemini API"
)
class LiveAcceptance(unittest.TestCase):
    def setUp(self):
        origin = os.environ.get("DEVMIND_API_URL", "http://127.0.0.1:8000").rstrip("/")
        target = httpx.URL(origin)
        if target.scheme != "https" and not (
            target.scheme == "http" and target.host in {"127.0.0.1", "localhost", "::1"}
        ):
            self.fail("Use HTTPS for a remote API or HTTP on loopback.")
        first, second = required("DEVMIND_OWNER_TOKEN"), required("DEVMIND_OTHER_TOKEN")
        self.owner = token_subject(first)
        self.assertNotEqual(self.owner, token_subject(second), "Use two distinct test accounts.")
        self.client = self.enterContext(
            httpx.Client(base_url=origin, timeout=180, headers={"Authorization": "Bearer " + first})
        )
        self.other = self.enterContext(
            httpx.Client(base_url=origin, timeout=30, headers={"Authorization": "Bearer " + second})
        )
        settings = dotenv_values(Path(__file__).resolve().parents[1] / "backend" / ".env")
        dsn = os.environ.get("DATABASE_URL") or settings.get("DATABASE_URL")
        if not dsn:
            self.fail(
                "Configure the running API's DATABASE_URL in the environment or backend/.env."
            )
        self.db = self.enterContext(psycopg.connect(dsn, autocommit=True, connect_timeout=10))
        self.db.execute("set default_transaction_read_only=on")
        self.db.execute("set search_path = devmind,extensions,public")

    def request(self, verb, path, *, expected=200, client=None, **kwargs):
        response = (client or self.client).request(verb, path, **kwargs)
        if response.status_code != expected:
            try:
                detail = response.json().get("detail")
            except (AttributeError, ValueError):
                detail = "Non-JSON response"
            self.fail(f"{verb} {path} returned HTTP {response.status_code}: {detail}")
        return response.json()

    def ready(self, path):
        deadline = time.monotonic() + int(os.getenv("DEVMIND_JOB_WAIT", "720"))
        while time.monotonic() < deadline:
            workspace = self.request("GET", path)
            job = workspace["job"]
            if job["status"] == "ready":
                return workspace
            if job["status"] == "failed":
                self.fail(f"Indexing failed: {job['error']}")
            time.sleep(2)
        self.fail("The indexer did not finish within DEVMIND_JOB_WAIT.")

    def verify_chunks(self, rid, sha):
        row = self.db.execute(
            """
            select count(*), count(distinct c.id), min(vector_dims(c.embedding)),
                   max(vector_dims(c.embedding)), min(vector_norm(c.embedding)), count(distinct c.path)
            from chunks c join repositories r on r.id=c.repo_id
            where r.id=%s and r.owner_id=%s and c.sha=%s""",
            (rid, self.owner, sha),
        ).fetchone()
        count, ids, min_dims, max_dims, min_norm, files = row
        self.assertGreater(count, 0)
        self.assertEqual(ids, count)
        self.assertEqual((min_dims, max_dims), (768, 768))
        self.assertGreater(min_norm, 0)
        self.assertGreater(files, 0)
        return count

    def check_sources(self, workspace, path, citations):
        self.assertTrue(citations, "Expected cited source evidence.")
        for source in citations:
            start, end = source["start_line"], source["end_line"]
            self.assertEqual(source["sha"], workspace["sha"])
            self.assertEqual(
                source["url"],
                f"{workspace['url']}/blob/{workspace['sha']}/{quote(source['path'])}#L{start}-L{end}",
            )
            file = self.request("GET", path + "/file", params={"path": source["path"]})
            lines = file["text"].splitlines()
            self.assertTrue(1 <= start <= end <= len(lines))
            self.assertIn(
                source["text"].strip().replace("\r\n", "\n"), "\n".join(lines[start - 1 : end])
            )

    def test_two_repository_workflows(self):
        self.assertEqual(self.request("GET", "/health")["configuration"], "configured")
        with httpx.Client(base_url=self.client.base_url) as anonymous:
            self.request("GET", "/repos", expected=401, client=anonymous)
        self.request("GET", "/repos", client=self.other)
        existing = {repo["url"] for repo in self.request("GET", "/repos")}
        urls = {f"https://github.com/{name}" for name, _, _ in CASES}
        self.assertFalse(
            existing & urls, "Use a dedicated owner account without either acceptance repository."
        )
        self.request("POST", "/repos", expected=422, json={"url": "https://example.invalid/repo"})
        relationships = 0
        for slug, source_path, question in CASES:
            url = f"https://github.com/{slug}"
            result = self.request("POST", "/repos", expected=202, json={"url": url})
            rid = str(UUID(result["id"]))
            path = "/repos/" + rid
            workspace = self.ready(path)
            self.assertTrue(re.fullmatch("[0-9a-f]{40}", workspace["sha"]))
            self.assertEqual(workspace["url"], url)
            self.assertIn(source_path, [f["path"] for f in workspace["files"]])
            metadata = workspace["metadata"]
            self.assertGreaterEqual(metadata["discovered"], len(workspace["files"]))
            self.assertTrue(metadata["languages"])
            self.assertTrue(workspace["symbols"])
            chunk_count = self.verify_chunks(rid, workspace["sha"])
            for suffix in ["", "/history", "/documents", "/file", "/impact"]:
                params = {"path": source_path} if suffix in {"/file", "/impact"} else {}
                self.request("GET", path + suffix, params=params, client=self.other, expected=404)
            payload = {"question": question}
            self.request("POST", path + "/search", json=payload, client=self.other, expected=404)
            search = self.request("POST", path + "/search", json=payload)
            self.check_sources(workspace, path, search)
            self.assertIn(
                source_path,
                [s["path"] for s in search],
                "Expected a relevant implementation file among the ranked results.",
            )
            answer = self.request("POST", path + "/ask", json={**payload, "path": source_path})
            self.check_sources(workspace, path, answer["citations"])
            self.assertTrue(all(s["path"] == source_path for s in answer["citations"]))
            self.assertTrue(answer["answer"].strip())
            references = set(re.findall(r"\[(S\d+)\]", answer["answer"]))
            self.assertTrue(references)
            self.assertTrue(references <= {s["label"] for s in answer["citations"]})
            doc = self.request(
                "POST",
                path + "/documents",
                json={"question": "Document what this repository does, citing the README."},
            )
            self.check_sources(workspace, path, doc["citations"])
            for edge in workspace["edges"]:
                if edge["kind"] != "internal":
                    continue
                relationships += 1
                dependants = self.request("GET", path + "/impact", params={"path": edge["target"]})[
                    "dependants"
                ]
                self.assertEqual(dependants[edge["source"]], 1)
                source = self.request("GET", path + "/file", params={"path": edge["source"]})
                line = source["text"].splitlines()[edge["line"] - 1]
                self.assertRegex(line, r"\b(import|from|require|export)\b")
            self.request("POST", path + "/refresh", expected=202)
            updated = self.ready(path)
            self.assertEqual(
                updated["sha"],
                workspace["sha"],
                "Upstream changed during the test. Review the new commit.",
            )
            self.assertEqual(
                sorted(f["path"] for f in updated["files"]),
                sorted(f["path"] for f in workspace["files"]),
            )
            self.assertEqual(self.verify_chunks(rid, updated["sha"]), chunk_count)
            for suffix, generated in [("/history", answer), ("/documents", doc)]:
                saved = self.request("GET", path + suffix)
                self.assertEqual(saved[-1]["answer"], generated["answer"])
                self.assertEqual(saved[-1]["citations"], generated["citations"])
            self.assertIn(rid, [repo["id"] for repo in self.request("GET", "/repos")])
            self.assertNotIn(
                rid, [repo["id"] for repo in self.request("GET", "/repos", client=self.other)]
            )
            print(
                slug,
                workspace["sha"],
                len(workspace["files"]),
                "files,",
                chunk_count,
                "vector-backed chunks",
            )
        self.assertGreater(
            relationships, 0, "Expected an actual internal dependency across the two projects."
        )
