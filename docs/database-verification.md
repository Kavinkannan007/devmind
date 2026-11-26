# Database verification

The SQL verification runs the production migration on a fresh in-memory PostgreSQL build using PGlite and pgvector. It creates the two Supabase browser roles and the auth.users primary key that the migration references. It does not require an account, a cloud database or API keys.

Run from the repository root with Node 22+ and pnpm.

```sh
pnpm --dir tests/db install --frozen-lockfile
node tests/db/verify.mjs
```

The migration and SQL assertions passed locally on November 26, 2026 with pgvector 0.8.7. Checks covered 768-dimensional vector storage, invalid-dimension rejection, cosine-distance ordering, duplicate active-job rejection, browser-role denial and cascading deletion of indexed data.

## API and database integration

Start the same isolated test database over the PostgreSQL wire protocol.

```sh
node tests/db/verify.mjs --serve
```

In another terminal with backend and test requirements installed, run the opt-in integration test. Use the disposable loopback server exclusively. The test creates two randomly identified account fixtures and deletes them when it exits.

```sh
DEVMIND_TEST_DATABASE_URL='postgresql://postgres@127.0.0.1:55439/postgres?sslmode=disable' \
  .venv/bin/python -m pytest -q tests/db/test_api_db.py
```

The test passed locally. It exercises FastAPI, psycopg, source parsing, dependency resolution, the indexing transaction, SQL hybrid search, citation validation and saved answers. The test uses isolated fixtures for GitHub content, Supabase identity and the Gemini SDK responses. A second identity checks repository, file, history, search, impact, refresh, document and deletion permissions. A fresh HTTP client checks saved state. The daily question quota and duplicate import behavior are checked through public endpoints.

The PGlite socket adapter multiplexes clients through a single underlying PostgreSQL session. The test calls the indexing routine directly, without starting the concurrent polling workers. Multi-session advisory locks, service restarts, Supabase token verification, real Gemini calls, and cloud load behavior require a hosted integration run. Stop the disposable server with Ctrl+C.

## Concurrent worker leases

The native PostgreSQL worker test passed independently of the single-session PGlite adapter. It starts one worker inside a job, contests both its slot and job locks from two more sessions, cancels the first worker and verifies that another worker can reclaim the interrupted job. An isolated provider failure then verifies that the scheduler persists the user-visible error. The test uses the production scheduler and a minimal jobs schema. It creates and removes one uniquely named test database on a disposable local PostgreSQL server.

```sh
DEVMIND_TEST_NATIVE_DSN='host=localhost dbname=postgres user=your_test_admin' \
  .venv/bin/python -m pytest -q tests/db/test_worker.py
```

The native test exercises connection cancellation and transaction cleanup. A hard process kill during a live provider request on Render still needs staging verification.
