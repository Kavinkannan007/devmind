# Live acceptance

## GitHub ingestion and parsing

From the repository root, run the opt-in test below. It reads two public GitHub repositories, parses their source, builds chunks, checks line ranges and prints the commit and observed counts. An optional read-only public-repository token in the process environment raises GitHub's anonymous quota.

```sh
DEVMIND_LIVE_GITHUB=1 .venv/bin/python -m pytest -q -s tests/test_github.py -k public_python_and_javascript
```

## Authenticated workflow

1. Apply the database migration to a Supabase test project, fill in the backend environment file and start DevMind. Set the frontend to the same project. Run the backend from the instructions in the root README.
2. Register and confirm two distinct test users. Use an owner account with neither of the two test repositories in its workspace. The other account exercises access control. Reserve **four imports and six question operations** in the owner's daily quotas for this run. The test calls the configured Gemini service and consumes its quota.
3. From the root, run the script below with the API at its default local address. For a deployed test environment, set `DEVMIND_API_URL` to its HTTPS origin first and confirm that the database connection and Supabase project match the API. Credentials stay in the local process. Enter both test accounts' passwords at the hidden prompts.

```sh
.venv/bin/python - <<'PY'
import getpass
import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv("backend/.env")
url = os.environ["SUPABASE_URL"].rstrip("/") + "/auth/v1/token"
headers = {"apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"]}
for label in ["OWNER", "OTHER"]:
    # getpass reads from the terminal when stdin carries this script.
    email = getpass.getpass(label + " test email (hidden): ")
    password = getpass.getpass(label + " test password: ")
    response = httpx.post(url, params={"grant_type": "password"}, headers=headers,
                          json={"email": email, "password": password}, timeout=15)
    if response.status_code != 200:
        raise SystemExit(f"{label} sign-in returned HTTP {response.status_code}")
    os.environ["DEVMIND_" + label + "_TOKEN"] = response.json()["access_token"]
os.environ["DEVMIND_LIVE"] = "1"
raise SystemExit(pytest.main(["-q", "-s", "tests/test_live.py"]))
PY
```

A CI secret manager can supply `DEVMIND_OWNER_TOKEN`, `DEVMIND_OTHER_TOKEN`, and a read-capable `DATABASE_URL` for the same project. Run `DEVMIND_LIVE=1 .venv/bin/python -m pytest -q -s tests/test_live.py` before the access tokens expire. A live run with missing required settings fails at setup. A normal unit-test run skips this suite.

The suite imports `pypa/sampleproject` and `sindresorhus/escape-string-regexp`, polls their persisted jobs and checks nonzero 768-dimensional vectors in PostgreSQL. It checks retrieval of known implementation files, each returned excerpt against its file and line range, generated answers, citations, saved documents, dependency impact, cross-account access and same-commit refresh. If upstream changes either repository during the run, inspect the new revision before repeating the test.

The test leaves both repositories in the owner's workspace for browser inspection. Sign in as the owner, open the saved conversation, click a citation and verify the Monaco tab and highlighted lines match the stored path and range. Refresh the browser and check the saved conversation and document. Sign in as the second user and verify the owner's workspace URL cannot be opened. Remove the two test repositories in Settings or use a fresh owner account for the next run.

The GitHub-only test can run independently of Supabase and Gemini. Its success verifies ingestion through chunking. A full authenticated acceptance result requires the separate live suite and browser checks above.
