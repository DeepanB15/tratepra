# API

Interactive docs: `http://localhost:8000/docs`.

| Method | Endpoint | Notes |
| --- | --- | --- |
| GET | `/health` | liveness |
| POST | `/api/research/search` | body `{query, sources[], time_range}`; returns answer, key findings, evidence, per-source status, distribution, related topics |
| GET | `/api/research/{id}` | stored result |
| GET | `/api/research/history` | previous queries |
| GET | `/api/trends` | filters: `lifecycle`, `q`, `min_sources` |
| GET | `/api/trends/{id}` | score, signals, coverage, related topics, representative documents |
| GET | `/api/trends/{id}/history` | one point per scoring run (+ per-window volumes) |
| GET | `/api/dashboard/overview` | metrics computed from stored data |
| GET | `/api/sources` | connector availability and last status |
| POST/GET/DELETE | `/api/saved`, `/api/saved/{id}` | saved items |
| POST | `/api/internal/collection/run` | body `{queries[], sources?, time_range}` |
| GET | `/api/internal/collection/status` | recent collection logs |
| POST | `/api/internal/trends/recompute` | run topic + trend pipeline |

Internal endpoints require header `X-Internal-Token: $INTERNAL_API_TOKEN`. Change the default value.


## v2.0 additions
- `POST /api/research/search` returns `422` for an empty/unsearchable query and for more than four sources. Response adds `degraded` (LLM unavailable, extractive fallback used), `transparency` (sources searched/failed, results collected, out-of-window, rejected, duplicates removed, accepted, candidates retrieved, evidence selected, claim statistics, per-stage timing in ms) and `unverified_claims` (statements removed because no valid, openable citation covered them).
- `GET /api/sources` adds `state` (`unavailable | configured | operational | failing`), `document_count`, `latest_document_at`, last fetched/accepted/duration. `configured` means credentials exist but no successful run has confirmed them.
- `GET /api/sources/logs?limit=` returns recent per-source collection runs.
- `GET /api/trends/{id}` adds `explanation` (summary, per-signal contribution points that sum to the score, missing signals with reasons), `source_distribution`, `weekly_volumes`, `previous_score`, `topic_size`.
- `GET /api/dashboard/overview` adds `active_topic_count`, `lifecycle_distribution`, `sources`, `recent_collections`; `document_count` is the stored-document count.
- `GET /health` (liveness), `GET /ready` (dependencies; `503` when database or pgvector fail).
- Errors are structured JSON `{"error", "detail"}`; unexpected errors return a `request_id` and never a stack trace. Request bodies over 64 KB get `413`.
