"""Importer regression tests and opt-in public GitHub acceptance checks."""

import hashlib
import io
import os
import unittest
import zipfile

import httpx

from backend.analysis import analyze, chunks
from backend.github import GitHubError, ingest, normalize_url, redact

URL = "https://github.com/example/project"
COMMIT = "a" * 40
TREE = "b" * 40
BLOB = "c" * 40
SOURCE = 'print("hello")\n'


def entry(path, **fields):
    item = {
        "path": path,
        "mode": "100644",
        "type": "blob",
        "sha": BLOB,
        "size": len(SOURCE),
    }
    return item | fields


def handler(entries, *, visibility="public", status=200, source=SOURCE, requests=None):
    base = "/repos/example/project"
    repo = {
        "name": "project",
        "private": visibility == "private",
        "visibility": visibility,
        "owner": {"login": "example"},
        "description": "",
        "stargazers_count": 2,
        "forks_count": 1,
        "updated_at": "2026-01-01",
        "default_branch": "release/main",
    }

    def receive(request):
        if request.url.host == "codeload.github.com":
            assert "Authorization" not in request.headers
            return httpx.Response(404)
        assert request.url.host == "api.github.com"
        assert request.method == "GET"
        if requests is not None:
            requests.append(request.url.path)
        if status != 200:
            return httpx.Response(status)
        part = request.url.path.removeprefix(base)
        if part == "/commits":
            assert request.url.params["sha"] == "release/main"
            return httpx.Response(200, json=[{"sha": COMMIT, "commit": {"tree": {"sha": TREE}}}])
        if part == f"/git/blobs/{BLOB}":
            return httpx.Response(200, content=source)
        return httpx.Response(
            200,
            json={
                "": repo,
                "/languages": {"Python": 1024},
                f"/git/trees/{TREE}": {"tree": entries, "truncated": True},
            }[part],
        )

    return httpx.MockTransport(receive)


class GitHubTests(unittest.IsolatedAsyncioTestCase):
    def test_normalization_and_rejection(self):
        self.assertEqual(normalize_url(" https://GitHub.com/Owner/Repo.git/ "), ("owner", "repo"))
        for url in [
            URL + "/tree/main",
            URL + "?x=1",
            URL + "#readme",
            "http://github.com/a/b",
            "https://github.com@localhost/a/b",
            "https://github.com/a/..",
            "https://github.com/a/b%2Fc",
            "https://github.com:443/a/b",
            "https://github.com/a/..%2fsecret",
        ]:
            with self.subTest(url=url), self.assertRaises(GitHubError):
                normalize_url(url)

    def test_redaction_preserves_lines(self):
        key = "a" * 30
        value = f'api_key = "{key}"\n-----BEGIN PRIVATE KEY-----\n{key}\n-----END PRIVATE KEY-----'
        safe = redact(value)
        self.assertNotIn(key, safe)
        self.assertEqual(safe.count("\n"), value.count("\n"))
        self.assertNotIn(key, redact("postgres://user:" + key + "@example/db"))

    def test_redaction_keeps_source_structure(self):
        code = "if token == value:\n    token = read_token()\n    return token"
        self.assertEqual(redact(code), code)

    async def test_bounded_import_and_progress(self):
        items = [
            entry(path)
            for path in [
                "README.md",
                "a.py",
                "b.py",
                "../a.py",
                "dist/large.js",
                ".env",
                "keys/credentials.json",
                "package-lock.json",
                "c.jpg",
                "env/.env.local",
                "d.min.js",
            ]
        ]
        items.extend([entry("link.py", mode="120000"), entry("large.py", size=900000)])
        progress = []

        async def report(stage, done, total):
            progress.append((stage, done, total))

        data = await ingest(URL, transport=handler(items), max_files=2, on_progress=report)
        self.assertEqual(data["metadata"]["sha"], COMMIT)
        self.assertEqual([f["path"] for f in data["files"]], ["README.md", "a.py"])
        self.assertEqual(data["files"][1]["source"], SOURCE)
        self.assertEqual(len(data["skipped"]), len(items) - 2)
        self.assertEqual(data["discovered"], len(items))
        self.assertTrue(data["truncated"])
        self.assertEqual(progress[-1], ("Downloading source files", 2, 2))

    async def test_size_and_binary_filters(self):
        response = await ingest(
            URL,
            transport=handler([entry("a.py"), entry("b.py")]),
            max_bytes=len(SOURCE),
        )
        self.assertEqual(response["skipped"][0]["reason"], "repository byte limit")
        for content in [b"\x00", b"\xff"]:
            response = await ingest(URL, transport=handler([entry("a.py")], source=content))
            self.assertEqual(response["skipped"][0]["reason"], "binary or non-UTF-8 content")
        with self.assertRaisesRegex(GitHubError, "byte limit"):
            await ingest(URL, transport=handler([entry("a.py", size=1)]))

    async def test_private_repo_stops_before_content(self):
        paths = []
        with self.assertRaisesRegex(GitHubError, "public"):
            await ingest(URL, transport=handler([], visibility="private", requests=paths))
        self.assertEqual(len(paths), 1)

    async def test_unchanged_revision_has_no_blob_requests(self):
        paths = []
        data = await ingest(URL, known_sha=COMMIT, transport=handler([], requests=paths))
        self.assertTrue(data["unchanged"])
        self.assertFalse(any("/git/" in p for p in paths))

    async def test_commit_archive_avoids_blob_requests(self):
        payload = SOURCE.encode()
        digest = hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()
        archive_data = io.BytesIO()
        with zipfile.ZipFile(archive_data, "w") as archive:
            archive.writestr(f"project-{COMMIT}/app.py", payload)
        api = handler([entry("app.py", sha=digest)])
        paths = []

        def receive(request):
            paths.append(request.url.path)
            if request.url.host == "codeload.github.com":
                self.assertEqual(request.url.path, f"/example/project/zip/{COMMIT}")
                self.assertNotIn("authorization", request.headers)
                return httpx.Response(200, content=archive_data.getvalue())
            return api.handle_request(request)

        result = await ingest(URL, token="test", transport=httpx.MockTransport(receive))
        self.assertEqual(result["files"][0]["source"], SOURCE)
        self.assertFalse(any("/git/blobs/" in path for path in paths))

    async def test_exhausted_quota_displays_provider_reset_time(self):
        response = httpx.Response(
            403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1795712630"}
        )
        transport = httpx.MockTransport(lambda request: response)
        with self.assertRaisesRegex(GitHubError, "2026-11-26 17:03:50 UTC"):
            await ingest(URL, transport=transport)

    async def test_github_errors(self):
        for status, message in [
            (301, "301"),
            (403, "rate limit"),
            (404, "unavailable"),
            (409, "no indexable"),
        ]:
            with (
                self.subTest(status=status),
                self.assertRaisesRegex(GitHubError, message),
            ):
                await ingest(URL, transport=handler([], status=status))


@unittest.skipUnless(os.getenv("DEVMIND_LIVE_GITHUB") == "1", "Opt-in live GitHub reads")
class LiveGitHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_python_and_javascript(self):
        for slug, expected in [
            ("pypa/sampleproject", "Python"),
            ("sindresorhus/escape-string-regexp", "JavaScript"),
        ]:
            with self.subTest(repo=slug):
                result = await ingest(
                    f"https://github.com/{slug}",
                    token=os.getenv("GITHUB_TOKEN"),
                    max_files=25,
                )
                files = result["files"]
                self.assertIn(expected, [f["language"] for f in files])
                self.assertTrue(any(f["source"].strip() for f in files))
                commit = result["metadata"]["sha"]
                count = symbols = 0
                for file in files:
                    parsed = analyze(file["path"], file["source"])
                    pieces = chunks(slug, commit, file["path"], file["source"], parsed)
                    count += len(pieces)
                    symbols += len(parsed["symbols"])
                    for piece in pieces:
                        self.assertGreaterEqual(piece["start_line"], 1)
                        self.assertLessEqual(piece["end_line"], len(file["source"].splitlines()))
                self.assertGreater(count, 0)
                print(
                    slug,
                    commit,
                    result["discovered"],
                    "discovered,",
                    len(files),
                    "indexed,",
                    count,
                    "chunks,",
                    symbols,
                    "symbols",
                )
