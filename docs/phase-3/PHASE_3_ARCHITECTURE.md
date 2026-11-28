# Phase 3 Architecture — Monitor

## Data flow
`TrendRun` (completed) → `TrendObservation` (snapshot) → **detection** → `TrendEvent` → **notification preparation** → `Notification` → UI.
Collection and recompute feed the snapshots; evidence association links new member documents and compares them with the latest dossier's claims.

## Tables (additive migration 005, idempotent, downgrade drops only these)
`trend_watchlist`, `trend_events`, `notifications`, `monitoring_preferences`, `monitoring_job_runs`. No observation, document or embedding is ever deleted by monitoring; unfollowing removes only the watchlist row.
`user_id` is nullable on watchlist and preferences with partial unique indexes, so per-user scoping can be added later; today the app is single-user and unauthenticated.

## Snapshots and comparability
Snapshot = observation joined to a run with `status='completed'`. Legacy observations without a run are excluded. Two snapshots are compared only if formula version is equal, window lengths agree within `MONITORING_WINDOW_TOLERANCE_DAYS`, and the earlier is older. Missing values (e.g. no growth) are never treated as zero; the event type is silently not evaluated and the reason is recorded in `suppressed`.

## Detection (`DETECTION_VERSION = cd-1`, pure functions, `MonitoringConfig`)
| Event | Rule (defaults) | Severity |
|---|---|---|
| growth_acceleration | growth +≥15 pp and volume +≥5 docs | important if ≥ 2× the pp threshold, else informational |
| growth_slowdown | growth drops ≥15 pp while still positive, volume change ≥5 | informational |
| activity_decline | volume −≥30% and ≥5 docs | informational; important at ≤ −60% |
| lifecycle_transition | lifecycle label changed | forward important, backward informational |
| activity_spike | volume ≥ baseline mean + 3 SD over ≥5 prior comparable snapshots and ≥1.5× (flat baseline: ratio rule) | important; critical at ≥3× |
| activity_disappearance | trend stale/inactive by completed-run bookkeeping | informational (stale), important (inactive) |
| new_emerging_trend | first snapshot, gated by docs/sources | important if score ≥70 |
| new_supporting_evidence | ≥3 member docs newer than previous snapshot | informational |
| contradictory_evidence | new doc's wording-heuristic contradicts a *supported/partially supported* claim of the latest dossier | important / informational |
| new_related_topic | topic embedding cosine ≥ 0.75 with a followed topic; **never merged** | informational |
| monitoring_failure | a job failed after retries | important |
Gating: volume < 8 docs or < 2 sources suppresses growth/decline/spike. Spike wording makes no significance claim (a deviation rule, not a hypothesis test). Contradiction is lexical/polarity-based, like Phase 2.

## Events, dedup, cooldown
`deduplication_key` (unique) includes the current observation id, so re-running detection cannot duplicate. Cooldown: the same event type for the same topic within `MONITORING_COOLDOWN_HOURS` is skipped unless severity is higher than the latest. Event state (new/read/dismissed/archived) is independent from notification state (read_at, dismissed_at).

## Explanations
Deterministic text assembled from stored values (previous/current values, thresholds, comparability, coverage, evidence count). Optional LLM rewrite (`MONITORING_LLM_EXPLANATIONS`) is accepted only if every number in the rewrite already appears in the deterministic text; any failure keeps the deterministic text.

## Scheduler and jobs
Jobs: collection → recompute → detection → evidence → notifications (cycle). Opt-in thread (`MONITORING_SCHEDULER_ENABLED`), interval `MONITORING_INTERVAL_MINUTES`, tick `MONITORING_TICK_SECONDS`.
- **Start:** due time derives from the last persisted cycle (restart-safe; no double run after restart). Interrupted `running` rows older than `MONITORING_RUNNING_TIMEOUT_MINUTES` are marked failed ("interrupted") at start.
- **Stop:** `stop()` sets an event; a cycle stops before the next job; the thread is joined at FastAPI shutdown.
- **Coordination:** one `pg_try_advisory_lock` per job name on a dedicated connection; a holder elsewhere → run recorded as `skipped`. Caveat: transaction-mode poolers (Supabase pgbouncer :6543) do not preserve session locks; use a direct/session connection.
- **Retries:** `MONITORING_JOB_MAX_ATTEMPTS` with delay; bounded, no infinite loop. Errors are sanitized before storage.
- **Failure policy:** collection failed → detection still runs but with `collection_failed` (no decline/disappearance events); recompute failed → detection and evidence skipped (no detection on incomplete observations); a `monitoring_failure` event + notification records failures. A failed cycle waits for the next interval.
- **Manual trigger:** `POST /api/internal/monitoring/run` (`X-Internal-Token`; 401 without; 409 if the job lock is held).

## Notifications
In-app only. Severities informational/important/critical. Preferences: minimum severity, muted event types, followed-only. Muted/low events still exist in Activity. Unread count, mark read, mark all read, dismiss, history.

## API (`/api/monitoring/*`)
overview, status, preferences, watchlist (GET/POST/PATCH/DELETE), trends/{id}, trends/{id}/history, trends/{id}/events, events, events/{id} (GET/PATCH), notifications, notifications/unread-count, notifications/mark-all-read, notifications/{id} (PATCH).

## UI
Monitor → Overview, Watchlist, Trend Monitoring Detail (`/monitor/trends/:id`), Activity, Notifications, Settings (preferences + read-only scheduler/job status); Follow button on the trend page; bell with unread count in the header.
