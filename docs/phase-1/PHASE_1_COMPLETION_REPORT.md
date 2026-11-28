# Phase 1 Completion Report

**Verdict: implementation complete and tested; NOT fully accepted.** Four acceptance criteria require your environment (see "Unmet / unverified").

## 1. What existed before
Working BERTopic + scoring pipeline and trend screens, but no run record, appended duplicate observations on every rerun, kept vanished topics in the active list, and had 4 failing tests.

## 2. Changed
`trend_service` split into `trend_run_service` (write) + `trend_service` (read); `preprocessor.prepare` (reasons, validation); `topic_model` (parameters exposed, recorded `min_df` fallback); `explain` (acceleration assessment, short summary); `/api/trends` (filters, sort, pagination, new fields, static routes); `health` (schema check); CORS exposes pagination headers; `run_trend_analysis.py` (`--dry-run`, exit codes); integration conftest (destructive-DB guard); frontend Layout, Home, Trends, TrendDetail, Sources, charts, ui, types, services.

## 3. Added
`TrendRun` model + migration 003; `run_key`, `freshness`, `topic_identity`, `topic_naming`, `topic_diagnostics` modules; overview + runs endpoints; `TrendRow`, Runs page; `evaluate_trend_quality.py`; 65 backend + 6 frontend tests; docs.

## 4. Database changes (migration `003_trend_runs`, additive + idempotent)
`trend_runs`; `trend_observations.run_id` + partial unique `(topic_id, run_id)`; `topics.last_run_id / last_observed_at / name_confidence / needs_review / review_reasons`; backfill of `last_observed_at`. Downgrade provided and tested. **Not applied to Supabase.**

## 5. Test results
162 backend passed, 11 frontend passed, build passes, browser e2e passes (details in PHASE_1_TEST_REPORT.md).

## 6. Real-data evaluation
Not run (no access). Tooling and protocol ready (TREND_QUALITY_REPORT.md).

## 7. Screens / workflows verified
Discovery Home, Trends, Trend Detail, Analysis Runs, Sources/data health; 8-step workflow, mobile width, error/retry — on synthetic data via real HTTP.

## Acceptance criteria
| Criterion | Status |
|---|---|
| Existing data intact; no destructive ops | ✅ no reset/delete/`down -v`; migration additive; Supabase untouched |
| Existing backend functionality operational | ✅ all original tests pass |
| Trend runs persisted | ✅ |
| Identical runs → no duplicate observations | ✅ tested |
| Failed runs don't corrupt prior observations | ✅ tested |
| BERTopic executes on the **actual** eligible dataset | ❌ not verified (synthetic only) |
| Topic quality diagnostics available | ✅ (values on real data pending) |
| Topic continuity tested | ✅ |
| Stale topics not shown as active | ✅ tested |
| Scores / missing signals explainable | ✅ |
| Discovery APIs work with real DB records | ✅ real PostgreSQL; ❌ not your Supabase data |
| Trend Detail shows real historical observations | ✅ (from stored observations) |
| Dashboard connected to backend; no mock data | ✅ |
| Backend unit tests / PG integration (isolated DB) pass | ✅ |
| Docker services start | ❌ not verified (no Docker daemon here) |
| Documentation complete | ✅ (quality report pending real run) |

## Known limitations
- Legacy duplicate observations from before this change remain (preserved, shown with `legacy` flag).
- A completed identical run key returns its original result even if stored topics changed since.
- Novelty is low for continuing topics by design (similar to a previously stored topic).
- "Rising" = lifecycle `growing`. Split/merge are similarity heuristics, not proof.
- English detection and name coverage are heuristics.
- `GET /api/trends` default now hides stale/inactive (`activity_state=all` restores old behaviour).
- Runs endpoints are unauthenticated read-only like other dashboard routes; recompute remains token-protected.
- The zip's `frontend/node_modules` was unusable here (Windows); builds were done in a clean install. Run `npm ci` locally.

## Deployment / run locally
```bash
# 1. back up, then apply the migration (stop writers first)
docker compose exec backend alembic upgrade head     # if DB was created by create_all only: alembic stamp 002 first
# 2. rebuild backend image (source is not volume-mounted); never use `down -v`
docker compose build backend && docker compose up -d
# 3. check
curl localhost:8000/ready          # includes "schema"
cd backend && python -m scripts.run_trend_analysis --dry-run     # safe preview
python -m scripts.evaluate_trend_quality                         # real-data quality tables
python -m scripts.run_trend_analysis                             # tracked, idempotent run
# tests (use a DISPOSABLE db; the guard rejects others)
set TEST_DATABASE_URL=postgresql+psycopg2://postgres:pw@localhost:5544/tratepra_it
pytest ; cd ../frontend && npm ci && npm test && npm run build
```

## Git commit recommendations (not committed)
1. `fix(tests): add text_hash to integration embedding helper; guard destructive test DB`
2. `feat(db): TrendRun model + idempotent migration 003`
3. `feat(trends): validation, diagnostics, naming, identity, idempotent recompute`
4. `feat(api): discovery list filters/sort/pagination, overview, runs, readiness schema check`
5. `feat(ui): discovery home, trend detail, runs, data health`
6. `docs: phase 1 reports`
**Do not commit** `backend/Dockerfile.backup`, `*.backup`, or `.env`. `embedding_store.py` and `test_embedding_store.py` changes were already in your working tree and are not mine — review them separately.

## Recommended Phase 2
Run + review real-data evaluation first; tune `min_cluster_size`/outlier handling only with that evidence; name-stability across runs; optional embedding-based language detection; authenticated admin controls; dossier/contradiction work as scoped.
