# DevMind verification status

Local checkpoint, 26 November 2026. The React frontend and FastAPI server run locally. External account configuration gates the first authenticated hosted import and Gemini answer.

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

1. Fill in the local backend and frontend environment files and apply the migration in a Supabase project. Values are listed in README.md. Keep private values in backend/.env.
2. Verify real Supabase registration, email confirmation and token validation. Run docs/live-tests.md with two dedicated users. Real Gemini embeddings, hosted vector persistence, answers and semantic relevance are still unverified. Browser tests used isolated services.
3. Confirm a private GitHub destination. Review staged content and credentials before any push.
4. Obtain publication approval, deploy, and verify actual production URLs, service restart behavior and both repositories again. No public deployment has been performed.
