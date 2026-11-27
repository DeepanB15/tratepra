"""Trend read side (discovery list, detail, history, overview, run diagnostics).

The write side lives in trend_run_service; `recompute` is re-exported for existing callers.

Activity state is derived at read time from COMPLETED runs (see app.intelligence.freshness), so stale topics are
never presented as active and a failed run never changes a topic's state.
"""
import bisect
import uuid
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.intelligence.explain import LABELS, acceleration_assessment, contributions, explain, short_summary
from app.intelligence.freshness import ACTIVE, INACTIVE, STALE, STATES, activity_state, config_from_settings
from app.intelligence.topic_representations import nearest_topics
from app.models import Document, DocumentEmbedding, Source, Topic, TopicDocument, TrendObservation, TrendRun
from app.services.trend_run_service import recompute, sanitize_error  # noqa: F401  (re-export)

SORT_KEYS = ("score", "growth", "momentum", "documents", "recent", "name")
LIFECYCLES = ("emerging", "growing", "peaking", "declining")
MOMENTUM = ("accelerating", "decelerating", "steady", "unknown")


# ---------------------------------------------------------------- shared context
def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class _Freshness:
    """Completed-run timeline used to derive activity state and 'data freshness'."""

    def __init__(self, db: Session):
        self.cfg = config_from_settings(get_settings())
        self.completed = [_aware(t) for t in db.scalars(select(TrendRun.completed_at).where(TrendRun.status == "completed").order_by(TrendRun.completed_at))]
        latest_obs = db.scalar(select(func.max(Topic.last_observed_at)))
        self.reference = self.completed[-1] if self.completed else _aware(latest_obs)

    def missed_runs(self, last_observed: datetime | None) -> int:
        if last_observed is None:
            return len(self.completed)
        return len(self.completed) - bisect.bisect_right(self.completed, _aware(last_observed))

    def state(self, last_observed: datetime | None) -> str:
        return activity_state(last_observed, self.reference, self.missed_runs(last_observed), self.cfg)


def _latest_observations(db: Session) -> dict[uuid.UUID, TrendObservation]:
    rows = db.scalars(select(TrendObservation).distinct(TrendObservation.topic_id).order_by(TrendObservation.topic_id, TrendObservation.created_at.desc())).all()
    return {o.topic_id: o for o in rows}


def _effective_last_observed(topic: Topic, obs: TrendObservation | None) -> datetime | None:
    return topic.last_observed_at or (obs.created_at if obs else None)


def _top_signal_label(o: TrendObservation) -> str | None:
    sig = {"growth": o.growth, "momentum": o.momentum, "engagement": o.engagement, "novelty": o.novelty, "search_interest": o.search_interest, "cross_source_activity": o.cross_source_activity}
    present = [r for r in contributions(sig) if r["points"] is not None]
    return max(present, key=lambda r: r["points"])["label"] if present else None


def _summary_row(t: Topic, o: TrendObservation, state: str, last_observed: datetime | None, fresh: _Freshness) -> dict:
    raw, cov = o.raw_signals or {}, o.coverage or {}
    volumes = raw.get("volumes", [])
    src = raw.get("source_counts", {})
    new_days = get_settings().trend_new_topic_days
    created = _aware(t.created_at)
    is_new = bool(fresh.reference and created and (fresh.reference - created).total_seconds() <= new_days * 86400)
    return {
        "topic_id": str(t.id),
        "topic_name": t.name,
        "trend_score": o.trend_score,
        "score_withheld": o.trend_score is None,
        "score_coverage": cov.get("signal_weight_coverage"),
        "lifecycle": o.lifecycle,
        "activity_state": state,
        "growth": raw.get("growth_pct"),
        "momentum_direction": raw.get("momentum_direction"),
        "momentum_pp": raw.get("momentum_pp"),
        "document_volume": o.document_volume,
        "supporting_documents": raw.get("topic_size"),
        "source_count": len(src) if src else cov.get("sources_observed", 0),
        "source_distribution": src,
        "coverage": cov,
        "sparkline": volumes,
        "is_new": is_new,
        "needs_review": bool(t.needs_review),
        "explanation": short_summary(o.trend_score, o.lifecycle, raw.get("growth_pct"), raw.get("momentum_direction"), volumes, cov, len(src), _top_signal_label(o)),
        "last_updated": o.created_at,
        "last_observed_at": last_observed,
        "first_seen_at": t.created_at,
    }


def _all_rows(db: Session) -> list[dict]:
    fresh = _Freshness(db)
    obs = _latest_observations(db)
    rows = []
    for t in db.scalars(select(Topic)).all():
        o = obs.get(t.id)
        if o is None:
            continue  # a topic with no observation has nothing to show
        last = _effective_last_observed(t, o)
        rows.append(_summary_row(t, o, fresh.state(last), last, fresh))
    return rows


def _sort_value(r: dict, key: str):
    if key == "score":
        return r["trend_score"]
    if key == "growth":
        return r["growth"]
    if key == "momentum":
        return r["momentum_pp"]
    if key == "documents":
        return r["supporting_documents"] or 0
    if key == "recent":
        return r["last_observed_at"]
    return r["topic_name"].lower()


# ---------------------------------------------------------------- discovery list
def search_trends(
    db: Session,
    lifecycle: str | None = None,
    q: str | None = None,
    min_sources: int | None = None,
    min_score: float | None = None,
    activity_state: str | None = ACTIVE,
    max_age_days: float | None = None,
    momentum_direction: str | None = None,
    is_new: bool | None = None,
    score_withheld: bool | None = None,
    sort: str = "score",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Filtered, sorted, paginated trends and the total match count. activity_state=None means every state."""
    rows = _all_rows(db)
    topics_by_id = None
    if q:
        topics_by_id = {str(t.id): t for t in db.scalars(select(Topic))}
    ref = _Freshness(db).reference if max_age_days is not None else None
    out = []
    for r in rows:
        if activity_state and r["activity_state"] != activity_state:
            continue
        if lifecycle and r["lifecycle"] != lifecycle:
            continue
        if momentum_direction and r["momentum_direction"] != momentum_direction:
            continue
        if is_new is not None and r["is_new"] != is_new:
            continue
        if score_withheld is not None and r["score_withheld"] != score_withheld:
            continue
        if min_sources and r["source_count"] < min_sources:
            continue
        if min_score is not None and (r["trend_score"] is None or r["trend_score"] < min_score):
            continue
        if max_age_days is not None:
            lo = _aware(r["last_observed_at"])
            if lo is None or ref is None or (ref - lo).total_seconds() > max_age_days * 86400:
                continue
        if q:
            t = topics_by_id[r["topic_id"]]
            ql = q.lower()
            if ql not in t.name.lower() and not any(ql in str(x).lower() for x in (t.terms or [])):
                continue
        out.append(r)

    # None values always sort last, in either direction.
    present = [r for r in out if _sort_value(r, sort) is not None]
    absent = [r for r in out if _sort_value(r, sort) is None]
    present.sort(key=lambda r: (_sort_value(r, sort), r["topic_name"].lower()), reverse=(order == "desc"))
    ordered = present + absent
    return ordered[offset: offset + limit], len(ordered)


def list_trends(db: Session, lifecycle: str | None = None, q: str | None = None, min_sources: int | None = None, limit: int = 50, **kw) -> list[dict]:
    """Backwards-compatible list (active trends, best score first)."""
    return search_trends(db, lifecycle=lifecycle, q=q, min_sources=min_sources, limit=limit, **kw)[0]


# ---------------------------------------------------------------- detail
def _run_info(db: Session, run_id) -> dict | None:
    if run_id is None:
        return None
    r = db.get(TrendRun, run_id)
    if r is None:
        return None
    return {"run_id": str(r.id), "status": r.status, "completed_at": r.completed_at, "model_version": r.model_version, "formula_version": r.formula_version, "documents_processed": r.documents_processed}


def trend_detail(db: Session, topic_id: str) -> dict:
    try:
        tid = uuid.UUID(topic_id)
    except ValueError:
        raise LookupError("Topic not found")
    t = db.get(Topic, tid)
    if t is None:
        raise LookupError("Topic not found")
    obs = db.scalars(select(TrendObservation).where(TrendObservation.topic_id == t.id).order_by(TrendObservation.created_at.desc()).limit(2)).all()
    o = obs[0] if obs else None
    prev = obs[1] if len(obs) > 1 else None
    fresh = _Freshness(db)
    last = _effective_last_observed(t, o)

    related, related_details = [], []
    if t.embedding is not None:
        others = {str(x.id): np.asarray(x.embedding, dtype=np.float32) for x in db.scalars(select(Topic).where(Topic.id != t.id, Topic.embedding.is_not(None)))}
        names = {str(x.id): x.name for x in db.scalars(select(Topic))}
        for k, sim in nearest_topics(np.asarray(t.embedding, dtype=np.float32), others, k=3):
            related.append(names[k])
            related_details.append({"topic_id": k, "name": names[k], "similarity": round(sim, 3)})

    q = (
        select(Document, Source.key)
        .join(TopicDocument, TopicDocument.document_id == Document.id)
        .join(Source, Source.id == Document.source_id)
        .where(TopicDocument.topic_id == t.id)
    )
    if t.embedding is not None:
        # representative = closest to the topic centroid (not just newest)
        q = q.join(DocumentEmbedding, DocumentEmbedding.document_id == Document.id).order_by(DocumentEmbedding.embedding.cosine_distance(t.embedding))
    else:
        q = q.order_by(Document.published_at.desc())
    docs = db.execute(q.limit(8)).all()

    signals = {k: (getattr(o, k) if o else None) for k in ("growth", "momentum", "engagement", "novelty", "search_interest", "cross_source_activity")}
    raw = (o.raw_signals or {}) if o else {}
    cov = (o.coverage or {}) if o else {}
    explanation = (
        explain(signals, o.trend_score, o.lifecycle, cov, raw.get("volumes", []), prev.trend_score if prev else None)
        if o
        else {"summary": "This topic has no trend observation yet.", "contributions": [], "missing": []}
    )
    accel = acceleration_assessment(raw.get("volumes", []), raw.get("momentum_direction"), raw.get("growth_flag")) if o else None
    if accel:
        explanation["acceleration"] = accel  # separate field; explain() already narrates spike vs sustained in the summary
    state = fresh.state(last) if o else INACTIVE
    return {
        "topic_id": str(t.id),
        "topic_name": t.name,
        "terms": t.terms,
        "trend_score": o.trend_score if o else None,
        "score_withheld": (o.trend_score is None) if o else True,
        "lifecycle": o.lifecycle if o else None,
        "activity_state": state,
        "signals": signals,
        "coverage": cov,
        "explanation": explanation,
        "growth_pct": raw.get("growth_pct"),
        "growth_flag": raw.get("growth_flag"),
        "momentum_direction": raw.get("momentum_direction"),
        "momentum_pp": raw.get("momentum_pp"),
        "document_volume": o.document_volume if o else None,
        "source_distribution": raw.get("source_counts", {}),
        "weekly_volumes": raw.get("volumes", []),
        "previous_score": prev.trend_score if prev else None,
        "topic_size": raw.get("topic_size"),
        "related_topics": related,
        "related_topic_details": related_details,
        "representative_documents": [{"id": str(d.id), "title": d.title, "url": d.url, "source": key, "published_at": d.published_at} for d, key in docs],
        "needs_review": bool(t.needs_review),
        "review_reasons": t.review_reasons or [],
        "name_confidence": t.name_confidence,
        "first_seen_at": t.created_at,
        "last_observed_at": last,
        "last_updated": o.created_at if o else None,
        "model_version": o.model_version if o else None,
        "formula_version": o.formula_version if o else None,
        "last_run": _run_info(db, o.run_id if o else None),
        "identity": cov.get("identity"),
    }


# ---------------------------------------------------------------- history
def trend_history(db: Session, topic_id: str, limit: int = 200) -> list[dict]:
    try:
        tid = uuid.UUID(topic_id)
    except ValueError:
        raise LookupError("Topic not found")
    if db.get(Topic, tid) is None:
        raise LookupError("Topic not found")
    rows = db.scalars(
        select(TrendObservation).where(TrendObservation.topic_id == tid).order_by(TrendObservation.window_end, TrendObservation.created_at).limit(limit)
    ).all()
    completed = {r.id: r.completed_at for r in db.scalars(select(TrendRun).where(TrendRun.id.in_({x.run_id for x in rows if x.run_id})))} if rows else {}
    out = []
    for r in rows:
        raw = r.raw_signals or {}
        out.append(
            {
                "window_start": r.window_start,
                "window_end": r.window_end,
                "observed_at": r.created_at,
                "document_volume": r.document_volume,
                "growth": raw.get("growth_pct"),
                "momentum": raw.get("momentum_pp"),
                "momentum_direction": raw.get("momentum_direction"),
                "trend_score": r.trend_score,
                "score_withheld": r.trend_score is None,
                "lifecycle": r.lifecycle,
                "run_id": str(r.run_id) if r.run_id else None,
                "run_completed_at": completed.get(r.run_id),
                "legacy": r.run_id is None,  # recorded before run tracking existed
                "created_at": r.created_at,
                "volumes": raw.get("volumes", []),
            }
        )
    return out


# ---------------------------------------------------------------- overview + runs
def _run_row(r: TrendRun, full: bool = False) -> dict:
    d = r.diagnostics or {}
    tq = d.get("topic_quality") or {}
    row = {
        "run_id": str(r.id),
        "run_key": r.run_key,
        "status": r.status,
        "started_at": r.started_at,
        "completed_at": r.completed_at,
        "window_end": r.window_end,
        "documents_available": r.documents_available,
        "documents_processed": r.documents_processed,
        "documents_rejected": r.documents_rejected,
        "noise_documents": r.noise_documents,
        "noise_percentage": tq.get("noise_percentage"),
        "topics_discovered": r.topics_discovered,
        "topics_created": r.topics_created,
        "topics_matched": r.topics_matched,
        "model_version": r.model_version,
        "formula_version": r.formula_version,
        "error_message": sanitize_error(r.error_message) if r.error_message else None,
        "attempts": d.get("attempts"),
        "topic_quality": ({k: v for k, v in tq.items() if k not in ("topic_sizes",)} if full else {k: tq.get(k) for k in ("noise_percentage", "topic_size", "run_flags", "cohesion") if k in tq}) or None,
    }
    if full:
        row.update(configuration=r.configuration, rejection=(d.get("prep") or {}), input=d.get("input"), identity=d.get("identity"))
    return row


def list_runs(db: Session, limit: int = 20, offset: int = 0, status: str | None = None) -> tuple[list[dict], int]:
    q = select(TrendRun)
    if status:
        q = q.where(TrendRun.status == status)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(func.coalesce(TrendRun.started_at, TrendRun.created_at).desc()).limit(limit).offset(offset)).all()
    return [_run_row(r) for r in rows], total


def get_run(db: Session, run_id: str) -> dict:
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise LookupError("Run not found")
    r = db.get(TrendRun, rid)
    if r is None:
        raise LookupError("Run not found")
    return _run_row(r, full=True)


def discovery_overview(db: Session) -> dict:
    s = get_settings()
    rows = _all_rows(db)
    by_state = {k: 0 for k in STATES}
    for r in rows:
        by_state[r["activity_state"]] += 1
    active = [r for r in rows if r["activity_state"] == ACTIVE]
    latest_ok = db.scalar(select(TrendRun).where(TrendRun.status == "completed").order_by(TrendRun.completed_at.desc()).limit(1))
    latest_any = db.scalar(select(TrendRun).order_by(func.coalesce(TrendRun.started_at, TrendRun.created_at).desc()).limit(1))
    now = datetime.now(timezone.utc)
    age_hours = None
    if latest_ok and latest_ok.completed_at:
        age_hours = round((now - _aware(latest_ok.completed_at)).total_seconds() / 3600, 1)
    ok_row = _run_row(latest_ok, full=True) if latest_ok else None
    return {
        "total_active_trends": len(active),
        "emerging_trends": sum(1 for r in active if r["lifecycle"] == "emerging"),
        "rising_trends": sum(1 for r in active if r["lifecycle"] == "growing"),
        "peaking_trends": sum(1 for r in active if r["lifecycle"] == "peaking"),
        "declining_trends": sum(1 for r in active if r["lifecycle"] == "declining"),
        "accelerating_trends": sum(1 for r in active if r["momentum_direction"] == "accelerating"),
        "new_trends": sum(1 for r in active if r["is_new"]),
        "withheld_score_trends": sum(1 for r in active if r["score_withheld"]),
        "needs_review_trends": sum(1 for r in active if r["needs_review"]),
        "stale_trends": by_state[STALE],
        "inactive_trends": by_state[INACTIVE],
        "activity_state_counts": by_state,
        "latest_successful_run": ok_row,
        "latest_run": _run_row(latest_any) if latest_any else None,
        "latest_run_status": latest_any.status if latest_any else None,
        "documents_analyzed": latest_ok.documents_processed if latest_ok else None,
        "topic_model_diagnostics": (ok_row or {}).get("topic_quality"),
        "data_freshness": {
            "latest_successful_analysis_at": latest_ok.completed_at if latest_ok else None,
            "age_hours": age_hours,
            "overdue": (age_hours is None) or age_hours > s.trend_analysis_overdue_days * 24,
            "overdue_after_days": s.trend_analysis_overdue_days,
        },
        "generated_at": now,
    }
