# Phase 3 Completion Report — Monitor

## Delivered
Persistent watchlist; snapshot comparison restricted to completed runs/comparable formula+window; deterministic configurable change detection (acceleration, slowdown, decline, lifecycle, spike, disappearance, new emerging trend, new evidence, possible contradiction, new related topic, monitoring failure); persistent events with dedup + cooldown; deterministic explanations (optional number-guarded LLM rewrite); opt-in scheduler with PostgreSQL advisory locks, bounded retries, restart recovery and a token-protected manual trigger; in-app notifications with preferences; six monitoring screens, follow button and notification bell; additive migration 005.

## Verified here (measured)
- Backend: **260 tests pass** (23 Phase-3 unit tests, 35 PostgreSQL integration tests covering watchlist, snapshots, dedup, cooldown, failure policy, advisory-lock concurrency incl. two racing threads, retries/sanitized errors, scheduler due/restart/stop, status, internal-trigger auth/409, constraints, migration 005 down/up/idempotent).
- Frontend: tsc clean, vite build OK, **19 vitest tests pass**.
- Browser e2e (`frontend/e2e/monitoring.e2e.cjs`, Playwright, isolated `*_e2e` DB, synthetic seed): 20/20 checks, stable over 3 fresh runs — follow persists, internal trigger auth, detection → events → notifications, bell count, mark-all-read keeps history, detail page, settings, preferences persist, no horizontal scroll at 390 px (a real overflow bug was found and fixed), unfollow keeps events, no console errors.
- Change-detection evaluation: 20/20 synthetic cases (see `CHANGE_DETECTION_REPORT.md`; synthetic only).

## Not verified
- No real corpus, real LLM or Supabase/Docker run. Thresholds are unvalidated defaults; real precision/recall is unknown.
- Scheduler was tested with injected job functions and a short tick, not for days of wall-clock operation.
- Advisory locks are verified on a direct PostgreSQL connection only; Supabase transaction-mode pooler does not preserve session locks (documented; use a direct/session connection).
- The e2e seed gives the current observation explicit synthetic scores because the tiny seeded corpus withholds scores (correctly: missing values are never treated as zero).
- Contradictory-evidence detection is a wording heuristic, not entailment.

## Notes
- Single-user, no auth: `/api/monitoring/*` is open like the rest of the app; `/api/internal/*` needs `X-Internal-Token`. `user_id` columns are ready for scoping.
- The Phase 3 prompt was truncated at Stage 11; the evaluation stage was inferred from Phase 1/2 conventions.
- Run e2e: start `backend/scripts/e2e_dev_server.py` (with `PYTHONPATH=backend`, `CORS_ORIGINS` for the web origin, `INTERNAL_API_TOKEN`), serve the built frontend, then `node frontend/e2e/monitoring.e2e.cjs`.
