# Tratepra — Consolidated Implementation & Project Status

Audit-only report. Every claim below comes from repository inspection or from commands run during this audit (2026-11-28). Nothing was changed, migrated, truncated or committed by this audit; this file is the only new file and is **uncommitted**. No secret values appear here.

**Evidence labels:** *[run]* = executed during this audit · *[last-run]* = executed earlier in this working session on the same code, not re-executed now (reason given) · *[read]* = read from code/docs · *[not run]* = never executed.

---

## 1. Implementation status

### Phase 1 — DISCOVER (commit `3fc12c3`, branch `phase-1-discovery-engine`)
- **Implemented [read]:** run-based trend analysis (`TrendRun` with idempotent `run_key`), topic identity across runs, freshness/activity states, trend score with withheld-score handling and coverage, lifecycle, momentum, novelty, explainability, discovery API (list/detail/history/overview/runs), discovery frontend.
- **Backend modules:** `app/intelligence/` (`trend_score`, `growth`, `lifecycle`, `momentum`, `novelty`, `freshness`, `topic_identity`, `topic_model`, `topic_naming`, `topic_diagnostics`, `explain`, `run_key`, …), `app/services/trend_run_service.py`, `trend_service.py`, `dashboard_service.py`; `app/evaluation/trend_quality.py`.
- **DB:** migration `003_trend_runs` (`trend_runs`; `trend_observations.run_id` etc.). Base tables from `001`, `002` (embedding text hash) pre-existed.
- **API:** `GET /api/trends`, `/overview`, `/runs`, `/runs/{id}`, `/{id}`, `/{id}/history`; `POST /api/internal/trends/recompute`.
- **Frontend:** `Home`, `Trends`, `TrendDetail`, `Runs`, shared `ui.tsx`, `Charts.tsx`, `TrendRow`.
- **Tests:** `test_phase1_units.py` (25), `test_trends_v2.py` (5), `test_intelligence.py` (15), integration `test_trend_runs.py` (17), `test_discovery_api.py` (11), `test_trends_dashboard.py` (1); `docs/phase-1/PHASE_1_TEST_REPORT.md`.
- **Incomplete / partial:** quality was measured only on synthetic/fixture data (`TREND_QUALITY_REPORT.md`); no real-corpus tuning.

### Phase 2 — INVESTIGATE (commits `e980dc5`, `98c2542`, `4f85408`, branch `phase-2-investigate-dossiers`)
- **Implemented [read]:** durable article-extraction states (full/partial/rss_only/unavailable/failed/too_short) with failure reasons; query-relevant excerpts that are the same text shown to the LLM and used for citation verification (fixes the Phase-2 audit defect); evidence selection with rejection reasons; research dossiers (sections: overview, key developments, supporting/contradictory evidence, entities, gaps, questions); deterministic claim extraction + lexical-overlap verification + polarity-cue contradiction detection; four-dimension evidence quality (no single confidence %); background generation with single-runner claim, stale reclaim, regeneration that keeps the previous result on failure; article refresh.
- **Backend modules:** `app/research/` (`excerpts`, `context_builder`, `claims`, `evidence_quality`, `dossier_engine`, `diagnostics`, `query_processor`, `retriever`, `ranker`, `synthesizer`, `citation_validator`), `app/ingestion/article_state.py`, `article_fetcher.py`, `article_refresh.py`, `article_enrichment.py`, `app/services/dossier_service.py`, `app/evaluation/research_quality.py`, `scripts/evaluate_research_quality.py`.
- **DB:** migration `004_article_evidence_dossiers`: 6 columns on `documents`; tables `research_dossiers`, `dossier_evidence`, `dossier_claims`, `claim_evidence`.
- **API:** `POST/GET /api/research/dossiers`, `GET /{id}`, `/{id}/evidence`, `/{id}/claims`, `POST /{id}/refresh`; existing `/api/research/search|history|{id}`.
- **Frontend:** `Dossier.tsx` (`/dossiers/:id`), `components/dossier/parts.tsx`, Investigate button on `TrendDetail`, `Research.tsx` (history, recent dossiers), `services/dossiers.ts`.
- **Tests:** `test_phase2_units.py` (21), `test_research_v2.py` (7), `test_article_fetcher.py` (5), `test_article_extractor.py` (3), integration `test_dossiers.py` (19), `test_research_pipeline.py` (3); `dossiers.test.ts`.
- **Incomplete / partial:** claim verification is a lexical heuristic, not entailment; no real LLM or real corpus was ever used (extractive fallback path only); the Phase-2 browser e2e script was kept in the session scratchpad and **is not in the repository**.

### Phase 3 — MONITOR (commits `f00fff3`, `d8509d8`, branch `phase-3-monitor`)
- **Implemented [read]:** watchlist; snapshot comparison limited to completed runs with equal formula version and window; deterministic configurable detection (growth acceleration, slowdown, decline, lifecycle transition, spike, disappearance, new emerging trend, new supporting evidence, possible contradiction vs latest dossier claims, new related topic, monitoring failure); persistent events with dedup keys and cooldown; deterministic explanations with optional number-guarded LLM rewrite; opt-in scheduler thread; per-job PostgreSQL advisory locks; bounded retries; interrupted-job recovery; failure policy; in-app notifications and preferences; token-protected manual trigger.
- **Backend modules:** `app/monitoring/` (`config`, `snapshots`, `detection`, `explanations`, `pipeline`, `jobs`), `app/services/monitoring_service.py`, `app/api/monitoring.py`, `app/api/internal.py` (+`/monitoring/run`), `app/models/monitoring.py`, `app/evaluation/change_detection.py`, `scripts/evaluate_change_detection.py`.
- **DB:** migration `005_monitoring`: `trend_watchlist`, `trend_events`, `notifications`, `monitoring_preferences`, `monitoring_job_runs`.
- **API (`/api/monitoring`):** `overview`, `status`, `preferences` (GET/PUT), `watchlist` (GET/POST/PATCH/DELETE), `trends/{id}`, `trends/{id}/history`, `trends/{id}/events`, `events`, `events/{id}` (GET/PATCH), `notifications`, `notifications/unread-count`, `notifications/mark-all-read`, `notifications/{id}` (PATCH). Internal: `POST /api/internal/monitoring/run`.
- **Frontend:** `pages/monitor/` (`MonitorOverview`, `Watchlist`, `TrendMonitor`, `Activity`, `Notifications`, `MonitorSettings`, `MonitorNav`), `components/monitor/parts.tsx` (Follow button, EventCard), notification bell in `Layout.tsx`, Follow/Monitoring buttons on `TrendDetail`, `services/monitoring.ts`.
- **Tests:** `test_phase3_units.py` (23), integration `test_monitoring.py` (35), `monitoring.test.ts` (5), Playwright `frontend/e2e/monitoring.e2e.cjs` (20 checks), `data/evaluation/change_cases.json` (20 cases).
- **Incomplete / partial:** thresholds are untuned defaults; no historical-accuracy data; scheduler never run for a real elapsed interval; the Phase-3 prompt was truncated at Stage 11, so the evaluation stage was inferred; the "Sources" page was moved out of the primary nav (now under the secondary links) — the old "Monitor" nav slot pointed at `/sources`.

---

## 2. Git status [run]

| Branch | Latest commit | Relation |
|---|---|---|
| `main` (= `origin/main`) | `389eb87` feat: improve ingestion and embedding reliability | base |
| `phase-1-discovery-engine` | `3fc12c3` | 1 commit ahead of main |
| `phase-2-investigate-dossiers` | `4f85408` | 4 commits ahead (contains Phase 1) |
| `phase-3-monitor` (**current**) | `d8509d8` | 6 commits ahead (contains Phase 1+2) |

Commits per phase — Phase 1: `3fc12c3`. Phase 2: `e980dc5` (audit), `98c2542` (engine/API), `4f85408` (frontend/eval/docs). Phase 3: `f00fff3` (backend), `d8509d8` (UI/eval/e2e/docs). The three branches form one linear chain; **no divergence and no conflicts** (each is 0 behind `main`/its parent).

**GitHub:** `origin` = `https://github.com/DeepanB15/tratepra.git`. **None of the three phase branches exist on the remote** (only `origin/main` does). Every push attempt fails with HTTP 403: "Claude doesn't have GitHub access to DeepanB15/tratepra" — the Claude GitHub App must be installed/reconnected by an org admin. Nothing from Phases 1–3 is backed up off this machine.

**Uncommitted (your pre-existing work, untouched):**
- `M backend/app/ingestion/embedding_store.py`
- `M backend/app/tests/test_embedding_store.py`
- `?? backend/Dockerfile.backup`
- `?? backend/app/tests/test_embedding_store.py.backup`
- plus the new, uncommitted `docs/PROJECT_COMPLETION_STATUS.md` (this report).
- `.env` exists and is git-ignored. No stashes exist.

Note: the Phase-2 audit assumed branch `phase-1-discovery-engine`; there is no PR open (no push possible).

---

## 3. Database status

**Migrations [read]:** `001_initial_schema` → `002_embedding_text_hash` → `003_trend_runs` → `004_article_evidence_dossiers` → `005_monitoring`. Single linear chain; **head = `005`**.

**Executed [run]:** both throw-away local databases on `localhost:5544` report `alembic_version = 005` with 22 public tables: `tratepra_it` (integration tests) and `tratepra_e2e` (browser e2e). Migration 005 down→004→up and idempotent re-upgrade is asserted by `test_migration_005_up_down_and_idempotent_with_create_all` [last-run, passing]; 004 up/down by `test_dossiers.py` [last-run]; 001 by earlier phases' tests. **Not executed against your real database or Supabase** — your `.env` `DATABASE_URL` points at a Supabase-style host and this audit made no connection to it.

**Tables added:** P1 `trend_runs` (+ columns on `trend_observations`); P2 `research_dossiers`, `dossier_evidence`, `dossier_claims`, `claim_evidence` (+6 `documents` columns); P3 `trend_watchlist`, `trend_events`, `notifications`, `monitoring_preferences`, `monitoring_job_runs`. Relationships: dossier→evidence/claims→`claim_evidence`→evidence; event→notification (unique, cascade); watchlist/event→`topics`; observation→`trend_runs`.

**Compatibility:** all three phases are additive and share one chain; no drops of Phase-1/2 objects; legacy observations (`run_id NULL`) are retained but excluded from monitoring. Migrations are written idempotent because `AUTO_CREATE_TABLES=true` lets `create_all` pre-create tables.

**Risks:**
1. Never run on Supabase from this environment; `docs/SUPABASE.md` itself says so.
2. Supabase transaction pooler (`:6543`/pgbouncer) does not keep session advisory locks → monitoring locks unreliable there; need session/direct connection.
3. With `AUTO_CREATE_TABLES=true` (your `.env` value) `create_all` may create tables without stamping `alembic_version`; then `alembic upgrade head` relies on migration idempotency — verified locally for 005 only with one table pre-created, not for 004 on a fully auto-created schema.
4. `001` requires permission to `CREATE EXTENSION vector`.
5. HNSW/GIN index builds on a large real corpus are untested.

---

## 4. Testing status

| Suite | Result | Evidence |
|---|---|---|
| Backend, no DB (`TEST_DATABASE_URL` unset) | **158 passed, 102 skipped** | [run] |
| Backend incl. PostgreSQL integration | **260 passed, 0 failed** (102 integration + 158 others) | [last-run] — not re-run now because those tests TRUNCATE their throw-away `tratepra_it`; 158 passed + 102 skipped = 260, equal to the last full-run total (of the 102 skips, 88 are itemised in the skip report as integration tests; the remaining 14 were not itemised in the output I captured) |
| Frontend vitest | **19 passed** (4 files) | [run] (from the `fe-build` copy; see issue K-8) |
| Frontend `tsc --noEmit` / `vite build` | clean / OK | [run] tsc; build [last-run] |
| Browser E2E (Playwright, monitoring) | **20/20 checks, stable over 3 fresh runs** | [last-run]; server stopped after the run |
| Change-detection evaluation | **20/20 synthetic cases; precision 1.0, recall 1.0** | [run] |
| Research-quality regression (synthetic) | P@5 1.0, MRR 1.0, nDCG@5 1.0, dup rate 0.0, Recall@5 0.5 | [last-run], synthetic |

**Not executed:** the Phase-1/Phase-2 browser e2e (scripts not in repo); `scripts/verify_setup`; anything against Docker, Ollama, Supabase or real sources; a long-running scheduler.

**Synthetic vs real-data:** *everything above is synthetic or fixture-based.* Integration tests use fake embeddings and hand-built rows; the e2e DB is seeded synthetically (current observation given explicit values); the change-detection cases were written by the detector's author and overlap the unit tests. **No real-data validation of any phase has been performed**, so real precision/recall of trends, retrieval, claim verification or change detection is unknown. A read-only replay on the 3-topic e2e DB produced only event counts.

---

## 5. Environment and deployment status

| Item | Tested? | Evidence |
|---|---|---|
| Docker Compose | **No** | Docker CLI exists but no daemon is reachable in this sandbox. The Dockerfile `CMD` does **not** run migrations; relies on `AUTO_CREATE_TABLES`. |
| Local Ollama | **No** | `ollama` binary absent. `.env` sets a model (`gemma3:1b`) but it was never contacted; all LLM paths exercised only via the extractive fallback or stubs. Compose points the container at `host.docker.internal:11434`. |
| Supabase PostgreSQL | **No** | `.env` `DATABASE_URL` host looks like Supabase; no connection was made (by design). |
| Existing env variables | **Partly read, not exercised** | Key names present: `APP_ENV` (=development), `AUTO_CREATE_TABLES` (=true), `DATABASE_URL`, pool sizes, Ollama, embedding model (`all-MiniLM-L6-v2`), YouTube/Reddit/Google-Trends keys, `INTERNAL_API_TOKEN` (43 chars, not the default), `CORS_ORIGINS`. New `MONITORING_*` variables are documented in `.env.example` only; `.env` was not edited. |
| Frontend ↔ backend | **Yes, synthetic backend** | Browser e2e (built frontend → FastAPI → local PostgreSQL) incl. CORS; not run against the real stack. |
| Scheduler | **Partly** | Unit/integration tests use injected jobs and 1-second ticks (start/stop/recover/due logic). Never run with real collection/recompute or across a real interval; disabled by default. |

---

## 6. Known issues

**Bugs / defects**
- K-1 `Watchlist` row building loads up to 30 snapshots per followed trend and `overview` fetches up to 500 rows → N+1 style queries; fine for tens of trends, unmeasured beyond. (Performance.)
- K-2 Monitoring e2e dispatch for internal triggers is asynchronous when `MONITORING_INLINE_EXECUTION=false`; the e2e had to poll (fixed in the test, not a product bug, but UI has no "running" indicator for manual runs).
- K-3 Notification bell polls every 60 s; no push/websocket (by design, in-app only).
- K-4 In the e2e, the 390 px layout was fixed for the Monitor tabs only; other pages were checked only for `/trends` overflow.

**Incomplete implementations**
- K-5 No Settings control to trigger jobs or edit the interval/thresholds from the UI (read-only status by design).
- K-6 Claim verification and contradiction detection are heuristics; the new-evidence-vs-dossier check compares against the *latest* dossier only.
- K-7 `docs/API_DOCUMENTATION.md`, `DATABASE_SCHEMA.md`, `IMPLEMENTED_VS_PLANNED.md`, `TESTING.md` contain **no mention** of dossiers or monitoring (grep = 0) — stale.
- K-8 Environment quirk: `vitest` in `frontend/node_modules/.bin` returned "Permission denied" here; tests were run from a copied tree. Unconfirmed whether it affects your machine.
- K-9 Phase-1/2 e2e scripts not committed; `frontend/e2e/mon_*.png` screenshots are committed artefacts that probably should not be.
- K-10 `frontend/package.json` has no e2e script or Playwright dependency; the e2e file relies on a globally available `playwright`.

**Untested workflows:** real collection → embed → recompute → detect → notify cycle; real Ollama dossiers/explanations (`MONITORING_LLM_EXPLANATIONS`); Docker Compose stack; Supabase migrations and advisory locks behind a pooler; multi-worker uvicorn with the scheduler enabled (locks should arbitrate but unverified); long-run scheduler; large-corpus performance.

**Security risks**
- S-1 The app has no authentication: all `/api/*` except `/api/internal/*` (token header) is open, including monitoring writes. Acceptable only for single-user local use.
- S-2 `INTERNAL_API_TOKEN` and CORS are only *enforced* when `APP_ENV=production`; current `.env` is `development`.
- S-3 The e2e server (`scripts/e2e_dev_server.py`) drops/creates a database; it is guarded (local host, name `*_e2e`) but is a foot-gun if guard logic is edited.
- S-4 Article fetching is SSRF-guarded (Phase 2) but was only tested with stubs.

**Deployment blockers**
- D-1 No Docker or Supabase validation. D-2 Dockerfile does not run `alembic upgrade head`. D-3 Pooler vs advisory locks (see §3). D-4 `AUTO_CREATE_TABLES=true` in `.env` for anything beyond development.

**GitHub access problem:** HTTP 403 on push for every branch; no remote copy of Phases 1–3 exists. Resolution: org admin installs/reconnects the Claude GitHub App for `DeepanB15/tratepra`, or you push the three branches yourself.

---

## 7. Recommendation — prioritized path to a working MVP

| # | Pri | Work | Files / modules | Verify by |
|---|---|---|---|---|
| 1 | P0 | Get the code off this sandbox: authorise GitHub, push the 3 branches, open PRs (Phase 1→main, 2→1, 3→2 or squash) | git remote, GitHub App install | `git ls-remote origin` lists all branches; PRs open |
| 2 | P0 | Decide what to do with your uncommitted `embedding_store.py` / test / `.backup` files (commit, discard, or ignore) so the tree is clean before merging | those 4 files, `.gitignore` | `git status` clean; `test_embedding_store.py` passes |
| 3 | P0 | Run migrations on a **copy** of the real DB (Supabase branch/dev project) using a session/direct connection; record in `RELEASE_CHECKLIST.md` | `backend/migrations/versions/001–005`, `docs/SUPABASE.md` | `alembic current` = 005; `python -m scripts.verify_setup` and `GET /ready` OK; down/up of 005 on the copy |
| 4 | P0 | Real-stack smoke test: `docker compose up --build` with real `.env`, local Ollama, real collection; fix issues found | `docker-compose.yml`, `backend/Dockerfile` (add migration step), `.env` | collect → recompute → open Discover → create dossier → follow trend → manual `monitoring/run` cycle all succeed with no errors in logs |
| 5 | P1 | Run one real collection + two recompute runs on real data and review trend quality, dossier grounding and events manually; tune `MONITORING_*` and discovery thresholds | `scripts/evaluate_trend_quality.py`, `evaluate_research_quality.py`, `evaluate_change_detection.py --replay`, `app/monitoring/config.py` | labelled review sheet of ≥ 50 trends/events with measured precision; report replaces the synthetic caveats in `RESEARCH_QUALITY_REPORT.md` / `CHANGE_DETECTION_REPORT.md` |
| 6 | P1 | Enable the scheduler for 48 h on the real stack and confirm cycles, locks, retries, recovery after restart | `app/monitoring/jobs.py`, `MONITORING_SCHEDULER_ENABLED` | `monitoring_job_runs` shows regular `cycle` rows, no duplicate events, restart does not double-run |
| 7 | P1 | Decide the auth model (even a shared token/basic auth for the whole API) before any non-local exposure; set `APP_ENV=production` for deployed runs | `app/main.py`, `app/core/exceptions.py`, `app/core/config.py` | unauthenticated `/api/monitoring/*` returns 401 in production mode; security-config tests extended |
| 8 | P2 | Update stale docs (API, schema, implemented-vs-planned, testing) for dossiers + monitoring | `docs/API_DOCUMENTATION.md`, `DATABASE_SCHEMA.md`, `IMPLEMENTED_VS_PLANNED.md`, `TESTING.md` | each lists every Phase-2/3 endpoint/table; spot-check vs `/openapi.json` |
| 9 | P2 | Commit the missing e2e scripts (Phase 1/2), add `playwright` + `e2e` script to `frontend/package.json`, remove committed screenshots, fix vitest bin permission if it reproduces | `frontend/package.json`, `frontend/e2e/` | `npm test` and `npm run e2e` pass from a clean clone |
| 10 | P2 | Watchlist/overview query efficiency and a "job running" indicator in Monitor Settings | `app/services/monitoring_service.py` (`_watch_row`, `overview`), `pages/monitor/MonitorSettings.tsx` | query count test with 200 followed trends; response time measured and recorded |
| 11 | P3 | Multi-worker/lock behaviour test; CI workflow running backend + vitest + e2e on a pgvector service | `.github/workflows/` (new), `tests/integration/test_monitoring.py` | green CI on PR; two-process scheduler test shows one cycle |

**Verdict:** all three phases are implemented, committed locally and pass 260 backend / 19 frontend / 20 browser-e2e / 20 synthetic-eval checks on a disposable local PostgreSQL. They are **not yet an MVP in the sense of being proven**: nothing has run on real data, Docker, Ollama or Supabase, and nothing is pushed. Items 1–4 are the gate.
