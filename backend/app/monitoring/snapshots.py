"""Monitoring snapshots = trend_observations that belong to a COMPLETED TrendRun.

Legacy observations (run_id NULL) are excluded: they cannot be proven to come from a successful run. Failed runs
write no observations (Phase 1 persists observations and run completion in one transaction), and the join below
re-checks the run status anyway.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TrendObservation, TrendRun


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


@dataclass(frozen=True)
class Snapshot:
    observation_id: str
    run_id: str
    topic_id: str
    observed_at: datetime  # when the successful run recorded it
    window_start: datetime
    window_end: datetime
    trend_score: float | None
    score_coverage: float | None
    growth: float | None  # percent (raw_signals.growth_pct); None = not measured (never treated as 0)
    momentum_pp: float | None
    momentum_direction: str | None
    novelty: float | None
    document_volume: int
    sources: int
    lifecycle: str | None
    formula_version: str
    model_version: str

    @property
    def window_days(self) -> float:
        return (self.window_end - self.window_start).total_seconds() / 86400.0


def to_snapshot(o: TrendObservation) -> Snapshot:
    raw, cov = o.raw_signals or {}, o.coverage or {}
    src = raw.get("source_counts") or {}
    return Snapshot(
        observation_id=str(o.id), run_id=str(o.run_id), topic_id=str(o.topic_id), observed_at=_aware(o.created_at),
        window_start=_aware(o.window_start), window_end=_aware(o.window_end), trend_score=o.trend_score,
        score_coverage=cov.get("signal_weight_coverage"), growth=raw.get("growth_pct"), momentum_pp=raw.get("momentum_pp"),
        momentum_direction=raw.get("momentum_direction"), novelty=o.novelty, document_volume=o.document_volume or 0,
        sources=len(src) if src else int(cov.get("sources_observed") or 0), lifecycle=o.lifecycle,
        formula_version=o.formula_version, model_version=o.model_version,
    )


def load_snapshots(db: Session, topic_id, limit: int = 200) -> list[Snapshot]:
    """Chronological (oldest first) snapshots from completed runs. At most `limit`, the most recent ones."""
    rows = db.scalars(
        select(TrendObservation)
        .join(TrendRun, TrendRun.id == TrendObservation.run_id)
        .where(TrendObservation.topic_id == topic_id, TrendRun.status == "completed")
        .order_by(TrendObservation.window_end.desc(), TrendObservation.created_at.desc())
        .limit(limit)
    ).all()
    return [to_snapshot(o) for o in reversed(rows)]


def comparable(prev: Snapshot, cur: Snapshot, window_tolerance_days: float = 1.0) -> tuple[bool, str]:
    """Whether two snapshots may be compared, with the reason when not.

    Not comparable: different scoring formula versions (no compatibility policy exists, so none is assumed),
    windows of different length (growth/volume are window-relative), or a previous snapshot that is not older."""
    if prev.window_end >= cur.window_end:
        return False, "previous snapshot is not older than the current one"
    if prev.formula_version != cur.formula_version:
        return False, f"scoring formula changed ({prev.formula_version} -> {cur.formula_version})"
    if abs(prev.window_days - cur.window_days) > window_tolerance_days:
        return False, f"window length differs ({prev.window_days:.1f}d vs {cur.window_days:.1f}d)"
    return True, "comparable"


def comparable_history(history: list[Snapshot], cfg_tolerance: float = 1.0) -> tuple[Snapshot | None, list[Snapshot], str]:
    """(current, comparable_prior_snapshots_oldest_first, note). Prior snapshots are those comparable with the current one."""
    if not history:
        return None, [], "no snapshots"
    cur = history[-1]
    prior, note = [], "comparable"
    for s in history[:-1]:
        ok, why = comparable(s, cur, cfg_tolerance)
        if ok:
            prior.append(s)
        else:
            note = why
    if not prior and len(history) > 1:
        return cur, [], note
    return cur, prior, "comparable" if prior else "no earlier snapshot"
