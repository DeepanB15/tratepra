# Phase 3 Audit — Monitoring

Inspected at branch `phase-2-investigate-dossiers` (Phase 1 commit `3fc12c3`, Phase 2 commits `e980dc5`…`4f85408`). The Phase 3 prompt says Phases 1 and 2 are complete; when it arrived Phase 2 was only audited. Phase 2 was therefore built first (see `docs/phase-2/`).

## Answers to the eight audit questions
1. **Persistent trend bookmarks?** `saved_items(item_type, item_id, title)` stores trend and research bookmarks with a unique `(item_type, item_id)`. It has no monitoring flag, priority, note, last-viewed time or user scope. It stays the lightweight "Save" bookmark; following a trend for monitoring needs its own table (`trend_watchlist`) so Saved is not overloaded and no second bookmark system is created for plain saving.
2. **User identity/scope?** None. No auth, no `user_id` anywhere; the app is single-user. Only `/api/internal/*` is protected, by a shared `X-Internal-Token`. New monitoring tables carry a nullable `user_id` and unique indexes that already separate "no user" from "per user", so scoping can be added later without a rewrite. Nothing here is safe for multiple users yet.
3. **Is trend history reliable?** For rows written since Phase 1: yes. `trend_observations` is append-only, one row per topic per run (partial unique index `uq_trend_obs_topic_run`), written in the same transaction that marks the `TrendRun` completed. Legacy rows (`run_id IS NULL`) predate run tracking and cannot be proven to come from a successful run.
4. **Observations tied to successful runs?** Yes for new rows (`run_id` FK, written only inside the completing transaction; failed runs record no observations). Monitoring uses only observations whose run is `completed` and ignores legacy rows.
5. **Stale vs inactive?** Yes: `intelligence/freshness.activity_state` counts *completed runs* the topic missed (default 1 → stale, 4 → inactive) plus age relative to the latest completed run, so failed runs and collection outages never age a topic.
6. **Can a dossier refresh be triggered safely?** Yes (Phase 2): `POST /api/research/dossiers/{id}/refresh`, single-runner conditional UPDATE, 409 if running, previous content kept on failure. Monitoring will not auto-regenerate dossiers; it only runs a cheap evidence check against the latest dossier.
7. **Existing scheduling?** None. No scheduler, cron or worker exists; collection and recompute run only via `scripts/*` or token-protected `/api/internal/collection/run` and `/api/internal/trends/recompute`. `docker-compose.yml` runs one backend container with no scheduler.
8. **Multiple backend instances running the same job?** Possible today (nothing coordinates). The recompute path is safe (idempotent run key + `_claim_run`). Collection is idempotent through content-hash dedup but wasteful. Phase 3 adds PostgreSQL advisory locks per job so only one instance executes a job.

## Existing monitoring-related capabilities
Run/observation history, activity state, lifecycle, momentum, novelty, source counts, `TrendRun` diagnostics, topic identity decisions (matched/uncertain/split/merge), related topics, dossiers + claim checks, collection logs, internal token auth, idempotent migrations.

## Missing
Watchlist, comparable-snapshot logic, change detection, persisted events, notifications and preferences, job-run records, scheduler, status endpoint, monitoring UI.

## Database changes (migration 005, additive and idempotent)
`trend_watchlist`, `trend_events`, `notifications`, `monitoring_preferences`, `monitoring_job_runs`. No existing table is altered. Deletion policy: removing a topic (never done by the app) cascades its watchlist rows and events; dismissing, archiving or unfollowing never deletes events or observations. `trend_observations` is reused as the snapshot store (no duplicate history).

## API contracts
Existing contracts are untouched. New: `/api/monitoring/*` (public, single-user) and `/api/internal/monitoring/*` (token-protected job triggers). Totals use `X-Total-Count`.

## Scheduling architecture
In-process scheduler thread, off by default (`MONITORING_SCHEDULER_ENABLED`). Due time is derived from the last persisted cycle, so restarts neither skip nor double-run. Per-job `pg_try_advisory_lock` on a dedicated connection prevents concurrent execution across instances. Jobs run in order: collection → recompute → detection → evidence → notification preparation, each recorded in `monitoring_job_runs`. Details in `PHASE_3_ARCHITECTURE.md`.

## Security risks
- No user model: followed trends, events and notification state are global. Documented, not hidden.
- Manual job triggers must stay behind the internal token; the token is never returned by any endpoint.
- Collection queries derived from watchlist names are sent to external connectors; they are bounded and sanitized (length, count).
- Stored errors pass through `sanitize_error`.
- A single scheduler per deployment is assumed; the advisory lock protects correctness, not throughput.
- Supabase pooled connections (pgbouncer transaction mode) do not preserve session advisory locks; the scheduler needs a direct or session-mode connection. Not verifiable here.

## Implementation plan
Models + migration → config → snapshot comparability → detectors → explanations → persistence/dedup/cooldown → evidence association → notifications/preferences → services/API → scheduler/jobs → frontend → evaluation → tests → docs.
