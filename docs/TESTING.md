# Testing

Run: `cd backend && pytest` (add `TEST_DATABASE_URL=...` for the PostgreSQL tests), `cd frontend && npm test`.

## What each layer proves

| Layer | Location | Proves | Does **not** prove |
| --- | --- | --- | --- |
| Unit | `backend/app/tests/test_*.py` | Pure logic: retry/backoff classification, date filter, dedupe, normalisation/validation, keyword + semantic ranking, evidence selection, claim verification, query processing, growth/momentum/novelty/score/lifecycle, language guard, topic matching, score explanation, evaluation metrics, security config, connector-state derivation | Behaviour of any real service |
| Integration (real PostgreSQL + pgvector) | `backend/app/tests/integration/` | Alembic upgrade/downgrade/upgrade, indexes and 384-d vector column, unique constraints, hybrid retrieval SQL (pgvector cosine + full-text), time-window/source filtering, research persistence, `/ready` against a real DB, trend detail/dashboard read paths, structured API errors | Real embedding quality, real LLM output, real connectors, Supabase specifics |
| Frontend | `frontend/src/services/__tests__/` | API client error handling (backend message surfaced, unreachable backend, non-JSON errors), age formatting; `tsc` + `vite build` | Visual regressions, user flows in a browser |

## Fakes, stated plainly
Integration tests replace the embedding model with a deterministic hash embedding, the LLM with a stub, and skip live collection (`refresh=False`). They are **pipeline tests**: they show the code wires up and persists correctly. They are not evidence that Ollama, Sentence Transformers, BERTopic, YouTube, Reddit, Google News or Google Trends work.

## Integration database
`TEST_DATABASE_URL` must point at a scratch database: the fixture drops the `public` schema and rebuilds it with `alembic upgrade head`. Without the variable these tests are skipped (reported as skipped, not passed).

Local example: PostgreSQL 16 with the `pgvector` package; create a database, then `TEST_DATABASE_URL=postgresql+psycopg2://postgres@localhost:5544/tratepra_it pytest`.

## Not covered by automated tests (verify manually, record in RELEASE_CHECKLIST)
- `trend_service.recompute` end to end with BERTopic on real documents (needs real, dated data and the BERTopic stack)
- Ollama synthesis with the configured Qwen model
- Each connector against its live service (`python -m scripts.verify_setup --probe`)
- Supabase connectivity (pooler/SSL)
- Browser-level UI flows

## Performance baselines
`app.evaluation.benchmark.time_it` times any callable. Per-stage timing of every research request (collection, embedding, retrieval, synthesis, total) is stored in `retrieval_metadata.transparency.timing_ms` and shown in the UI; collect real numbers from your environment before quoting any.
