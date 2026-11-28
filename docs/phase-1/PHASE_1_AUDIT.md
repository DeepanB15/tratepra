# Phase 1 Audit (Stage 0)

Audited against the repository as uploaded, before any change. Findings below were verified in source, not assumed.

## Existing capabilities
- FastAPI + SQLAlchemy 2 + Alembic (001 initial, 002 embedding `text_hash`), pgvector `Vector(384)` embeddings stored per document.
- Pipeline `trend_service.recompute()`: stored embeddings → BERTopic (UMAP → HDBSCAN → c-TF-IDF, seeded `random_state=42`, min 20 docs) → one-to-one centroid matching (`match_topics`, threshold `trend_topic_match_threshold`) → growth / momentum / engagement / novelty / search-interest / cross-source signals → `trend_score` with coverage-based **withholding** → lifecycle → `TrendObservation` rows.
- `explain.py` (contributions, missing signals, spike-vs-sustained narration), `lifecycle.py`, `preprocessor.py` (length, English heuristic, exact-duplicate removal).
- Read API `/api/trends` (list/detail/history), dashboard overview, internal recompute endpoint (token-protected), React dashboard (Home, Trends, TrendDetail, Sources, Research…).
- Baseline tests: 93 passed, **4 failed** (see risks).

## Observations confirmed in live source
| # | Observation | Confirmed |
|---|---|---|
| 1 | `recompute()` generated a new run id and appended observations on every call | yes |
| 2 | Re-running identical data appended duplicate observations | yes |
| 3 | Topics absent from newer runs stayed in the discovery list (read side had no staleness notion) | yes |
| 4 | One-to-one centroid matching | yes |
| 5 | BERTopic minimum of 20 docs | yes |
| 6 | Score withholding supported | yes |
| 8 | Topic modeling uses stored embeddings | yes |
| 9 | Existing trend screens exist | yes |
Additional: document rejection was only counted in aggregate (no per-reason accounting); no run record existed; `N_WINDOWS` was a module constant; `TrendObservation` had no link to a run.

## Missing capabilities (addressed in Phase 1)
Run tracking + idempotency, input validation with reasons, topic-quality diagnostics, evidence-based naming with review flags, split/merge/uncertain identity, activity state (active/stale/inactive), paginated/filterable discovery API, overview + run diagnostics endpoints, discovery UI, runs UI, evaluation tooling.

## Database migration requirements
Additive migration `003_trend_runs`: new table `trend_runs`; `trend_observations.run_id` (nullable FK + partial unique index `(topic_id, run_id) WHERE run_id IS NOT NULL`); `topics.last_run_id`, `last_observed_at`, `name_confidence`, `needs_review`, `review_reasons`. Backfills `last_observed_at` from existing observations. Nothing deleted or rewritten.

## Known technical risks found
1. **4 pre-existing failing tests** — the integration helper inserted `DocumentEmbedding` without the `text_hash` column made NOT NULL by migration 002. Fixed in the test helper only.
2. **Integration tests drop `public` schema** of `TEST_DATABASE_URL`. A mistaken URL would wipe a real database. A guard now refuses remote-managed hosts and names without `test`/`_it`.
3. **`AUTO_CREATE_TABLES=true` + new migration**: `create_all` creates missing tables but never adds columns, so a later `alembic upgrade head` could fail on "table exists". Migration 003 is now idempotent (tested).
4. BERTopic fits its vectorizer on per-topic documents, so `min_df=2` can prune every term when topics share no vocabulary (the run crashed). A recorded fallback to `min_df=1` was added; default unchanged.
5. Legacy duplicate observations from earlier repeated runs cannot be told apart from legitimate history; they are preserved and flagged `legacy` (no run id).
6. Backend source is not volume-mounted: rebuild the image after code changes.

## Uncommitted work present at audit time (not touched)
`backend/app/ingestion/embedding_store.py`, `backend/app/tests/test_embedding_store.py` (modified) and untracked `backend/Dockerfile.backup` (**do not commit**). Left exactly as found.

## Existing tests that must keep passing
All 93 originals (scoring, matching, lifecycle, explanations, dashboard, research, retrieval). They pass (plus the 4 repaired).
