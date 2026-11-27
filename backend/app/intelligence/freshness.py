"""Operational activity state (pure). Distinct from the analytical lifecycle.

active    - observed in the latest completed run, or only recently absent
stale     - not seen in recent completed runs; shown separately, never as a live trend
inactive  - not seen for a long time; hidden from discovery by default

Everything is measured against COMPLETED runs and relative to the latest completed run, never against the
wall clock alone. A failed run records no observation and moves nothing, so it cannot age a topic, and a
collection outage does not turn missing data into "no activity".
"""
from dataclasses import dataclass
from datetime import datetime, timezone

ACTIVE, STALE, INACTIVE = "active", "stale", "inactive"
STATES = (ACTIVE, STALE, INACTIVE)


@dataclass(frozen=True)
class FreshnessConfig:
    stale_after_missed_runs: int = 1
    inactive_after_missed_runs: int = 4
    stale_after_days: float = 14.0
    inactive_after_days: float = 45.0


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def activity_state(
    last_observed_at: datetime | None,
    reference_time: datetime | None,
    missed_runs: int,
    cfg: FreshnessConfig | None = None,
) -> str:
    """missed_runs: completed runs that finished after the topic's last observation.
    reference_time: completion time of the latest completed run (None when there is none)."""
    cfg = cfg or FreshnessConfig()
    last, ref = _aware(last_observed_at), _aware(reference_time)
    if last is None:
        return INACTIVE  # never observed: nothing to show as live
    age_days = max(0.0, (ref - last).total_seconds() / 86400.0) if ref is not None else 0.0
    if missed_runs >= cfg.inactive_after_missed_runs or age_days >= cfg.inactive_after_days:
        return INACTIVE
    if missed_runs >= cfg.stale_after_missed_runs or age_days >= cfg.stale_after_days:
        return STALE
    return ACTIVE


def config_from_settings(s) -> FreshnessConfig:
    return FreshnessConfig(
        stale_after_missed_runs=s.trend_stale_after_missed_runs,
        inactive_after_missed_runs=s.trend_inactive_after_missed_runs,
        stale_after_days=s.trend_stale_after_days,
        inactive_after_days=s.trend_inactive_after_days,
    )
