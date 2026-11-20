# Implementation plan (v2.0 hardening)

Applied against the existing code; no module was rebuilt. Status is only what the evidence in `IMPLEMENTED_VS_PLANNED.md` supports.

| WS | Scope | Main changes | Status |
| --- | --- | --- | --- |
| 1 | Database / infra | Alembic initial migration, HNSW + GIN + composite indexes, unique constraints, `/health` + `/ready`, `APP_ENV` security checks, pool settings, rollback on request errors | Done; verified on local PostgreSQL+pgvector; Supabase not verified |
| 2 | Ingestion / connectors | Shared pipeline with validation and run-level collection logs, state derived from facts (never "operational" from config), Google Trends endpoint config + strict parser, retry/backoff | Done; live connectors not verified (need keys/network) |
| 3 | Research | Hybrid retrieval, normalised ranking, diverse evidence selection, claim-level citation verification, transparency stats + timing, honest fallback, 422 on bad queries | Done; quality unmeasured (no labels) |
| 4 | Trends | Stopword-ratio language guard, one-to-one topic matching with configurable threshold, lifecycle spike guard and plateau fix, score explanations, source distribution | Done; BERTopic run on real data not verified |
| 5 | Frontend | Dashboard (real counts, lifecycle distribution, source freshness, recent collections), research transparency + removed claims, Sources monitoring page, trend explanation panel, committed lockfile, vitest | Done; verified by build + screenshots + unit tests |
| 6 | Security / reliability | Constant-time token check, body-size limit, structured errors, no stack traces | Done |
| 7 | Testing / evaluation | Unit + real-PostgreSQL integration tests, evaluation package, datasets, `verify_setup` | Done; retrieval dataset needs human labels |
| 8 | Docs / deployment | README, SUPABASE, TESTING, EVALUATION, RELEASE_CHECKLIST, API docs | Done |

## Bugs found and fixed by the new tests
- Malformed research id raised a database error (HTTP 500) instead of 404.
- Dashboard "recent activity" linked with the query id instead of the result id (links 404'd).
- Flat series classified "peaking".
- `source_status` held datetimes in a JSON column (would fail on persistence).

## Out of scope (per PRD)
Agents/MCP, content generation, extra connectors, Redis/Kafka/Kubernetes, separate vector DB, multi-user auth, forecasting.
