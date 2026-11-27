# DevMind verification status

Local checkpoint, 26 November 2026. The React frontend and FastAPI server run locally. See the hosted verification update below for the current integration status.

## Implemented

- Public GitHub ingestion pinned to the default branch commit, safe file filters, bounded source downloads, credential redaction and coverage reporting.
- Durable jobs, retries and refreshes, atomic snapshot replacement, per-user quotas and processing-slot locks.
- Python, JavaScript and TypeScript analysis, symbol-aware chunks, real SDK calls for embedding and generation, repository-scoped pgvector and lexical retrieval, server-validated citations and saved history.
- Email authentication, personal profile, repository library, Monaco source viewer, semantic search, React Flow graph, dependency traversal, analytics, saved documentation and Markdown export.
- Supabase SQL migration, Vercel SPA configuration, Render Blueprint, environment files, local Git history and release instructions.

## Observed checks

| Check | Observed result |
| --- | --- |
| Live GitHub, pypa/sampleproject | Commit 621e4974ca25ce531773def586ba3ed8e736b3fc. 12 discovered, 8 indexed, 16 chunks, 7 symbols. Source spans checked. |
| Live GitHub, sindresorhus/escape-string-regexp | Commit a7f7dabaf336bda98d2166848af15d9168b10bcf. 13 discovered, 6 indexed, 6 chunks, 1 symbol. Source spans checked. |
| Combined Python suite with GitHub and local database tests enabled | 22 passed, 18 subtests passed, 1 hosted acceptance test skipped. |
| SQL migration and FastAPI persistence | Local PostgreSQL via PGlite with pgvector 0.8.7. Checked vector dimensionality and ranking, cross-user denial, saved answers/docs, duplicate jobs, snapshots, daily quotas and deletion. AI and identity responses were isolated test fixtures. |
| Worker concurrency | Native PostgreSQL sessions excluded competing workers and reclaimed a cancelled worker's job. A provider failure persisted the error. |
| Frontend build | TypeScript, ESLint and Vite production build passed. Monaco loads on demand. |
| Browser | Chrome at 1440px and 390px verified the landing layout. Authenticated production-build regression with isolated services passed, including exact citation line highlighting, mobile exploration, refresh, saved chat and document export. |
| Backend lint | Ruff passed. |

## Resolved failures

The machine's bundled Node executable rejected Rollup's native module signature. The build and local server succeeded using a checksum-verified portable Node distribution. The authenticated browser test initially typed into the Overview assistant during navigation. Waiting for the Ask DevMind heading fixed the test. No known failing assertions remain in the executed suites.

## External blockers and remaining work

1. Backend and frontend credentials are configured. The hosted migration and vector round trip are verified below.
2. Verify real Supabase registration, email confirmation and token validation. Run docs/live-tests.md with two dedicated users. The remaining hosted check is a complete authenticated import, cited answer and two-account isolation test. Browser tests used isolated services.
3. Confirm a private GitHub destination. Review staged content and credentials before any push.
4. Obtain publication approval, deploy, and verify actual production URLs, service restart behavior and both repositories again. No public deployment has been performed.

## Hosted verification update

On 26 November 2026, the free DevMind Supabase project accepted the reset database password over its TLS session pooler. The production migration ran successfully. A fresh query verified `devmind.repositories` and pgvector 0.8.2. The local frontend returned HTTP 200 and the API reported all required configuration present. A live Gemini SDK request returned a 768-dimensional embedding.

The originally configured generation model returned HTTP 503 for high demand. The legacy Flash-Lite endpoint returned HTTP 404 for new users. On the same public input, gemini-3.5-flash-lite returned an answer citing index.js lines 1–11. DevMind now uses that verified model in the private local environment.

A real Gemini embedding round-tripped through a temporary Supabase pgvector table with 768 dimensions and cosine self-distance 0.0. The full public pypa/sampleproject ingestion, embedding, retrieval and answer pipeline passed against disposable local pgvector storage with 16 real vectors and a source citation at src/sample/simple.py lines 1–2. GitHub exhausted its anonymous quota before the second complete import. DevMind now reports the exact provider reset timestamp when available. Hosted two-user acceptance awaits dedicated test-account approval.

On 27 November 2026, the Vespera Stays import completed at commit `8d00ee92` with 21 eligible source files and 136 embeddings stored in Supabase. The first attempt reached Gemini's rate limit at 64 chunks. The retry recovered after a cooldown and kept the completed batches in memory. A live DevMind answer cited `README.md` lines 1–43 and `src/app/page.tsx` lines 26–59 and was saved to the workspace. This check invoked the application service with the existing workspace owner. The separate two-account sign-in and isolation test remains pending.

A completed import now keeps its chunk totals during the save stage and after reaching Ready. The local API and pgvector integration test verified the final counts and checked access from a second fixture identity. The running local API reported configured and rejected unauthenticated repository access with HTTP 401. Frontend lint, type checking and the production build passed.

## Public deployment

DevMind is published at [devmind-vin.vercel.app](https://devmind-vin.vercel.app) from the [public GitHub repository](https://github.com/Kavinkannan007/devmind). The [Render API](https://devmind-vin-api.onrender.com/health) runs on the free instance type. Public checks returned HTTP 200 for the frontend, sign-in page, repository route, API health and Vercel-origin CORS preflight. The API returned HTTP 401 for unauthenticated repository access. Supabase uses the production domain as its Site URL and allows the exact /repositories confirmation redirect. A signed-in production import and answer still need verification. Earlier live GitHub, Supabase and Gemini workflow checks used the local API.
