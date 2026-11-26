"""Fetch public, immutable GitHub blobs into memory. No checkout or code execution."""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath

import httpx

Progress = Callable[[str, int, int], Awaitable[None]]


class GitHubError(ValueError):
    """Import failure with a message suitable for the job owner."""


_REPO = re.compile(
    r"https://github\.com/([a-z0-9][a-z0-9-]{0,38})/([a-z0-9_.-]{1,104})/?",
    re.IGNORECASE | re.ASCII,
)
_HASH = re.compile(r"[0-9a-f]{40}")
_LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".mts": "TypeScript",
    ".cts": "TypeScript",
    ".md": "Markdown",
    ".mdx": "MDX",
    ".rst": "reStructuredText",
    ".txt": "Text",
    ".json": "JSON",
    ".toml": "TOML",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".sql": "SQL",
    ".sh": "Shell",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".hpp": "C++",
    ".cs": "C#",
    ".dart": "Dart",
}
_SKIP_DIR = {
    "node_modules",
    "dist",
    "build",
    "vendor",
    "__pycache__",
    "venv",
    "target",
    "coverage",
    "out",
    "generated",
    "bower_components",
    "third_party",
    "site-packages",
    "credentials",
    "secrets",
    "pods",
    "__snapshots__",
}
_LOCKS = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "bun.lockb",
    "bun.lock",
}
_SECRET_FILE = re.compile(
    r"(^|[._-])(secret[s]?|credential[s]?|password[s]?|private[_-]?key|service[_-]?account|"
    r"access[_-]?token|auth[_-]?token|keystore|id_rsa|id_ed25519)([._-]|$)"
)
_PRIVATE_BLOCK = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)"
)
_TOKEN = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"(?:AKIA|ASIA)[A-Z0-9]{16}|AIza[0-9A-Za-z_-]{30,}|sk[-_][a-zA-Z0-9_-]{16,}|"
    r"xox[baprs]-[\w-]{10,}|eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"
)
_ASSIGNMENT = re.compile(
    r"""(?im)(\b[\w.-]*(?:api[_-]?key|access[_-]?key|password|passwd|secret|token|private[_-]?key)[\w.-]*["']?[ \t]*[:=](?!=)[ \t]*)(?:"[^"\r\n]+"|'[^'\r\n]+'|[\w+/=-]{12,}(?=[ \t]*(?:$|[,;}#])))"""
)
_AUTH = re.compile(r"(?i)(\b(?:Bearer|Basic)[ \t]+)[A-Za-z0-9._~+/=-]{8,}")
_DSN = re.compile(r"(\b[a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s@]+:[^/\s@]+@")


def normalize_url(url: str) -> tuple[str, str]:
    match = _REPO.fullmatch(url.strip())
    if match:
        owner, name = match.groups()
        name = name.removesuffix(".git")
        if name and name not in {".", ".."} and len(name) <= 100:
            return owner.lower(), name.lower()
    raise GitHubError("Enter a public repository URL in the form https://github.com/owner/repo.")


def redact(source: str) -> str:
    def mask_block(match):
        return "\n".join("[REDACTED]" for _ in match.group().split("\n"))

    source = _PRIVATE_BLOCK.sub(mask_block, source)
    source = _ASSIGNMENT.sub(r'\1"[REDACTED]"', source)
    source = _AUTH.sub(r"\1[REDACTED]", source)
    source = _DSN.sub(r"\1[REDACTED]@", source)
    return _TOKEN.sub("[REDACTED]", source)


def _language(path: str) -> str | None:
    filename = PurePosixPath(path).name.lower()
    if filename in {"readme", "makefile", "dockerfile"}:
        return {"readme": "Text", "makefile": "Makefile", "dockerfile": "Dockerfile"}[filename]
    return _LANGUAGES.get(PurePosixPath(filename).suffix)


def _skip_reason(item: dict, maximum: int) -> str | None:
    path = item["path"]
    parts = path.lower().split("/")
    name = parts[-1]
    if (
        any(part in {"", ".", ".."} for part in parts)
        or "\\" in path
        or any(ord(char) < 32 or ord(char) == 127 for char in path)
    ):
        return "unsafe path"
    if item.get("mode") not in {"100644", "100755"}:
        return "link or submodule"
    if (
        any(p.startswith(".") or p in _SKIP_DIR for p in parts)
        or _SECRET_FILE.search(name)
        or _TOKEN.search(path)
        or name in _LOCKS
        or name.endswith(".lock")
        or ".min." in name
        or ".bundle." in name
        or ".generated." in name
    ):
        return "excluded by file policy"
    if not _language(path):
        return "unsupported file type"
    if not isinstance(item.get("size"), int) or not 0 < item["size"] <= maximum:
        return "empty or outside file size limit"
    return None


class _API:
    def __init__(self, client: httpx.AsyncClient, owner: str, name: str):
        self.client = client
        self.base = f"https://api.github.com/repos/{owner}/{name}"

    async def read(self, suffix="", *, params=None, raw=False, limit=2_000_000):
        headers = {"Accept": "application/vnd.github.raw+json"} if raw else {}
        for attempt in range(3):
            try:
                async with self.client.stream(
                    "GET", self.base + suffix, params=params, headers=headers
                ) as r:
                    status = r.status_code
                    if status in {403, 429}:
                        raise GitHubError(
                            "GitHub denied the request or reached its rate limit. Check token permissions and retry after the limit resets."
                        )
                    if status == 401:
                        raise GitHubError(
                            "GitHub rejected the configured token. Check GITHUB_TOKEN."
                        )
                    if status == 404:
                        raise GitHubError(
                            "Repository or revision unavailable. Check the URL and public visibility."
                        )
                    if status == 409:
                        raise GitHubError("This repository has no indexable commit yet.")
                    if status in {500, 502, 503, 504} and attempt < 2:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
                    if status != 200:
                        raise GitHubError(
                            f"GitHub returned HTTP {status}. Check the repository URL and retry."
                        )
                    data = bytearray()
                    async for piece in r.aiter_bytes(chunk_size=65536):
                        if len(data) + len(piece) > limit:
                            raise GitHubError(
                                "A GitHub response exceeded the importer's byte limit."
                            )
                        data.extend(piece)
                    return bytes(data) if raw else json.loads(data)
            except httpx.RequestError:
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                raise GitHubError("GitHub could not be reached. Please retry the import.") from None


def _sha(value: str) -> str:
    if not _HASH.fullmatch(value):
        raise GitHubError("GitHub returned an invalid object identifier.")
    return value


async def ingest(
    url: str,
    *,
    token=None,
    max_files=300,
    max_bytes=5 * 1024 * 1024,
    max_file_bytes=200 * 1024,
    timeout=300,
    on_progress: Progress | None = None,
    known_sha=None,
    transport=None,
) -> dict:
    """Fetch up to the configured count, text size and wall-clock limits."""

    async def progress(stage, done=0, total=0):
        if on_progress:
            await on_progress(stage, done, total)

    await progress("Validating repository")
    owner, name = normalize_url(url)
    headers = {"User-Agent": "DevMind-indexer", "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with (
            asyncio.timeout(timeout),
            httpx.AsyncClient(
                headers=headers,
                timeout=20,
                follow_redirects=False,
                transport=transport,
            ) as client,
        ):
            api = _API(client, owner, name)
            await progress("Fetching repository metadata")
            repo = await api.read()
            if repo.get("private") is not False or repo.get("visibility") != "public":
                raise GitHubError("Only public repositories can be imported.")
            branch = repo["default_branch"]
            commits = await api.read("/commits", params={"sha": branch, "per_page": 1})
            if not commits:
                raise GitHubError("This repository has no commits yet.")
            latest = commits[0]
            sha = _sha(latest["sha"])
            metadata = {
                "name": repo["name"],
                "owner": repo["owner"]["login"],
                "description": redact(repo.get("description") or ""),
                "default_branch": branch,
                "stars": repo["stargazers_count"],
                "forks": repo["forks_count"],
                "updated_at": repo["updated_at"],
                "sha": sha,
                "languages": await api.read("/languages"),
                "url": f"https://github.com/{owner}/{name}",
            }
            result = {
                "metadata": metadata,
                "files": [],
                "skipped": [],
                "discovered": 0,
                "truncated": False,
                "unchanged": known_sha == sha,
            }
            if result["unchanged"]:
                return result
            await progress("Retrieving file tree")
            tree_id = _sha(latest["commit"]["tree"]["sha"])
            tree = await api.read(
                f"/git/trees/{tree_id}", params={"recursive": "1"}, limit=12_000_000
            )
            entries = [e for e in tree["tree"] if e["type"] != "tree"]
            result.update(discovered=len(entries), truncated=bool(tree.get("truncated")))
            candidates, budget = [], 0
            # Keep the top-level README available for overview and onboarding questions.
            for entry in sorted(
                entries,
                key=lambda e: (not e["path"].lower().startswith("readme"), e["path"]),
            ):
                path = entry["path"]
                reason = _skip_reason(entry, max_file_bytes)
                if not reason:
                    if len(candidates) >= max_files:
                        reason = "file count limit"
                    elif budget + entry["size"] > max_bytes:
                        reason = "repository byte limit"
                if reason:
                    result["skipped"].append(
                        {"path": _TOKEN.sub("[REDACTED]", path), "reason": reason}
                    )
                    continue
                candidates.append(entry)
                budget += entry["size"]
            await progress("Downloading source files", 0, len(candidates))
            indexed_bytes = 0
            for pos, entry in enumerate(candidates, start=1):
                path = entry["path"]
                blob_id = _sha(entry["sha"])
                raw = await api.read(
                    f"/git/blobs/{blob_id}",
                    raw=True,
                    limit=min(max_file_bytes, entry["size"]),
                )
                try:
                    source = raw.decode("utf-8")
                except UnicodeDecodeError:
                    source = ""
                if not source or any(ord(c) < 32 and c not in "\t\r\n\f" for c in source):
                    reason = "binary or non-UTF-8 content"
                elif source.startswith("version https://git-lfs.github.com/spec/v1"):
                    reason = "Git LFS pointer"
                elif any(len(line) > 6000 for line in source.splitlines()):
                    reason = "generated or exceptionally long line"
                else:
                    source = redact(source)
                    size = len(source.encode("utf-8"))
                    if size > max_file_bytes or indexed_bytes + size > max_bytes:
                        reason = "redacted text exceeds byte limit"
                    else:
                        result["files"].append(
                            {
                                "path": path,
                                "language": _language(path),
                                "source": source,
                                "size": size,
                            }
                        )
                        indexed_bytes += size
                        reason = None
                if reason:
                    result["skipped"].append(
                        {"path": _TOKEN.sub("[REDACTED]", path), "reason": reason}
                    )
                await progress("Downloading source files", pos, len(candidates))
            return result
    except TimeoutError:
        raise GitHubError(
            "The repository import timed out. Try a smaller repository or retry later."
        ) from None
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise GitHubError("GitHub returned an unexpected response. Please retry.") from None
