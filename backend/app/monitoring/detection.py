"""Deterministic, explainable change detection. Pure functions: snapshots + config in, event candidates out.

Every candidate carries the exact values, thresholds and comparability note that produced it. Rules never
treat a missing value as zero, never compare snapshots that fail `comparable`, and report what they suppressed
and why (`Detection.suppressed`) so quiet runs are explainable too.
"""
from dataclasses import dataclass, field
from math import sqrt

from app.monitoring.config import DETECTION_VERSION, MonitoringConfig
from app.monitoring.snapshots import Snapshot, comparable_history

SEV_RANK = {"informational": 0, "important": 1, "critical": 2}
FORWARD = {("emerging", "growing"), ("growing", "peaking"), ("peaking", "declining")}
COOLDOWN_TYPES = {"growth_acceleration", "growth_slowdown", "activity_decline", "activity_spike", "new_supporting_evidence", "contradictory_evidence"}


@dataclass
class EventCandidate:
    event_type: str
    severity: str
    title: str
    dedup_key: str
    topic_id: str
    previous_value: float | None = None
    current_value: float | None = None
    change_percentage: float | None = None
    previous_observation_id: str | None = None
    current_observation_id: str | None = None
    evidence_document_ids: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    explanation: str = ""
    description: str = ""
    detection_version: str = DETECTION_VERSION


@dataclass
class Detection:
    events: list[EventCandidate] = field(default_factory=list)
    suppressed: list[dict] = field(default_factory=list)


def _pct(prev: float, cur: float) -> float | None:
    return None if not prev else round((cur - prev) / abs(prev) * 100.0, 1)


def _gate(cur: Snapshot, cfg: MonitoringConfig) -> str | None:
    if cur.document_volume < cfg.min_documents:
        return f"document volume {cur.document_volume} is below the minimum of {cfg.min_documents}"
    if cur.sources < cfg.min_sources:
        return f"{cur.sources} source(s) observed; at least {cfg.min_sources} required"
    return None


def _base(kind: str, sev: str, title: str, prev: Snapshot | None, cur: Snapshot, key_tail: str, **kw) -> EventCandidate:
    return EventCandidate(
        event_type=kind, severity=sev, title=title, topic_id=cur.topic_id, dedup_key=f"{cur.topic_id}:{kind}:{cur.observation_id}{key_tail}",
        previous_observation_id=prev.observation_id if prev else None, current_observation_id=cur.observation_id, **kw,
    )


def detect(history: list[Snapshot], cfg: MonitoringConfig, *, topic_name: str, collection_failed: bool = False,
           activity: dict | None = None, is_new_topic: bool = False) -> Detection:
    """history: chronological completed-run snapshots of ONE topic. activity: {"state", "missed_runs", "last_observed_at"}."""
    out = Detection()
    cur, prior, note = comparable_history(history, cfg.window_tolerance_days)
    if cur is None:
        return out
    meta_base = {"comparability": note, "thresholds": {}, "topic": topic_name, "formula_version": cur.formula_version,
                 "comparable_observations": len(prior), "sources": cur.sources, "score_coverage": cur.score_coverage}

    # H. activity disappearance: from completed-run bookkeeping only; never inferred during a collection failure.
    if activity and activity.get("state") in ("stale", "inactive"):
        if collection_failed:
            out.suppressed.append({"type": "activity_disappearance", "reason": "collection failed this cycle; absence cannot be attributed to the topic"})
        else:
            st = activity["state"]
            out.events.append(_base(
                "activity_disappearance", "important" if st == "inactive" else "informational",
                f"{topic_name} is now {st}", None, cur, f":{st}",
                details={**meta_base, "metric": "activity_state", "state": st, "missed_runs": activity.get("missed_runs"),
                         "last_observed_at": str(activity.get("last_observed_at"))},
            ))
            out.events[-1].previous_observation_id = cur.observation_id

    # New emerging trend: the topic's first snapshot, recently created, classified emerging.
    if is_new_topic and len(history) == 1 and cur.lifecycle == "emerging":
        why = _gate(cur, cfg)
        if why:
            out.suppressed.append({"type": "new_emerging_trend", "reason": why})
        elif cfg.emerging_min_score and (cur.trend_score is None or cur.trend_score < cfg.emerging_min_score):
            out.suppressed.append({"type": "new_emerging_trend", "reason": "score below the configured minimum or withheld"})
        else:
            sev = "important" if cur.trend_score is not None and cur.trend_score >= cfg.emerging_important_score else "informational"
            out.events.append(_base("new_emerging_trend", sev, f"New emerging trend: {topic_name}", None, cur, "",
                                    current_value=cur.document_volume, details={**meta_base, "metric": "document_volume", "unit": "documents", "trend_score": cur.trend_score}))

    if len(prior) < cfg.min_observations - 1:
        out.suppressed.append({"type": "comparison", "reason": f"{len(prior) + 1} comparable observation(s); {cfg.min_observations} required ({note})"})
        return out
    prev = prior[-1]
    meta = {**meta_base, "previous_observed_at": str(prev.observed_at), "previous_window_end": str(prev.window_end), "current_window_end": str(cur.window_end)}

    # D. lifecycle transition
    if prev.lifecycle and cur.lifecycle and prev.lifecycle != cur.lifecycle:
        sev = "important" if (prev.lifecycle, cur.lifecycle) in FORWARD else "informational"
        out.events.append(_base("lifecycle_transition", sev, f"{topic_name}: {prev.lifecycle} → {cur.lifecycle}", prev, cur, f":{prev.lifecycle}>{cur.lifecycle}",
                                details={**meta, "metric": "lifecycle", "from": prev.lifecycle, "to": cur.lifecycle, "forward": (prev.lifecycle, cur.lifecycle) in FORWARD}))

    gate = _gate(cur, cfg)
    for kind in ("growth_acceleration", "growth_slowdown", "activity_decline", "activity_spike"):
        if gate:
            out.suppressed.append({"type": kind, "reason": gate})
    if gate:
        return out

    vol_change = cur.document_volume - prev.document_volume

    # A / B. growth acceleration / slowdown (growth values are percentages; a missing value is skipped, not zero)
    if prev.growth is None or cur.growth is None:
        out.suppressed.append({"type": "growth_acceleration", "reason": "growth was not measured in one of the observations"})
    else:
        delta = cur.growth - prev.growth
        thr = {"min_growth_change_pp": cfg.min_growth_change_pp, "min_volume_change": cfg.min_volume_change}
        if cur.growth > 0 and delta >= cfg.min_growth_change_pp and vol_change >= cfg.min_volume_change:
            sev = "important" if delta >= 2 * cfg.min_growth_change_pp else "informational"
            out.events.append(_base("growth_acceleration", sev, f"{topic_name}: growth accelerating", prev, cur, "",
                                    previous_value=prev.growth, current_value=cur.growth,
                                    details={**meta, "metric": "growth_pct", "unit": "pp", "change_points": round(delta, 1), "volume_change": vol_change,
                                             "previous_volume": prev.document_volume, "current_volume": cur.document_volume, "thresholds": thr}))
        elif prev.growth > 0 and cur.growth > 0 and -delta >= cfg.min_growth_change_pp:
            out.events.append(_base("growth_slowdown", "informational", f"{topic_name}: growth slowing", prev, cur, "",
                                    previous_value=prev.growth, current_value=cur.growth,
                                    details={**meta, "metric": "growth_pct", "unit": "pp", "change_points": round(delta, 1), "volume_change": vol_change,
                                             "previous_volume": prev.document_volume, "current_volume": cur.document_volume, "thresholds": thr}))

    # C. activity decline (relative AND absolute drop); not evaluated when collection failed
    pct = _pct(prev.document_volume, cur.document_volume)
    if collection_failed:
        out.suppressed.append({"type": "activity_decline", "reason": "collection failed this cycle; a volume drop cannot be attributed to the topic"})
    elif pct is not None and pct <= -cfg.decline_pct and -vol_change >= cfg.min_volume_change:
        sev = "important" if pct <= -2 * cfg.decline_pct else "informational"
        out.events.append(_base("activity_decline", sev, f"{topic_name}: activity declining", prev, cur, "",
                                previous_value=prev.document_volume, current_value=cur.document_volume, change_percentage=pct,
                                details={**meta, "metric": "document_volume", "unit": "documents", "volume_change": vol_change,
                                         "thresholds": {"decline_pct": cfg.decline_pct, "min_volume_change": cfg.min_volume_change}}))

    # I. unusual spike relative to the recent comparable baseline (descriptive deviation, NOT a significance test)
    base = prior[-cfg.spike_baseline_window:]
    if len(base) < cfg.spike_baseline_window:
        out.suppressed.append({"type": "activity_spike", "reason": f"{len(base)} baseline observation(s); {cfg.spike_baseline_window} required"})
    else:
        vols = [b.document_volume for b in base]
        mean = sum(vols) / len(vols)
        std = sqrt(sum((v - mean) ** 2 for v in vols) / len(vols))
        ratio = cur.document_volume / mean if mean else None
        z = (cur.document_volume - mean) / std if std > 0 else None
        big_enough = (cur.document_volume - mean) >= cfg.min_volume_change and ratio is not None and ratio >= cfg.spike_min_ratio
        deviates = (z >= cfg.spike_z) if z is not None else True  # flat baseline: the absolute/ratio rules decide
        if big_enough and deviates:
            sev = "critical" if ratio >= cfg.critical_spike_ratio else "important"
            out.events.append(_base("activity_spike", sev, f"{topic_name}: unusual activity spike", base[-1], cur, "",
                                    previous_value=round(mean, 1), current_value=cur.document_volume, change_percentage=_pct(mean, cur.document_volume),
                                    details={**meta, "metric": "document_volume", "unit": "documents", "baseline_mean": round(mean, 2), "baseline_std": round(std, 2),
                                             "baseline_n": len(base), "baseline_values": vols, "ratio": round(ratio, 2), "z": None if z is None else round(z, 2),
                                             "statistical_test": "none: z is a descriptive deviation from the recent baseline, not a significance test",
                                             "thresholds": {"spike_z": cfg.spike_z, "spike_min_ratio": cfg.spike_min_ratio, "min_volume_change": cfg.min_volume_change,
                                                            "critical_spike_ratio": cfg.critical_spike_ratio}}))
        else:
            out.suppressed.append({"type": "activity_spike", "reason": "current volume is within the normal range of the recent baseline"})
    return out
