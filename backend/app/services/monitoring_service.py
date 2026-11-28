"""Monitoring read/write services: watchlist, trend monitoring detail, events, notifications, preferences, status."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Document, MonitoringJobRun, MonitoringPreference, Notification, ResearchDossier, Topic, TrendEvent, TrendRun, TrendWatchlist,
)
from app.monitoring import pipeline
from app.monitoring.snapshots import Snapshot, comparable, load_snapshots
from app.services.trend_service import _Freshness

SEV_ORDER = {"informational": 0, "important": 1, "critical": 2}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(value, what: str = "Item") -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except ValueError:
        raise LookupError(f"{what} not found")


def _snap(s: Snapshot | None) -> dict | None:
    if s is None:
        return None
    return {"observation_id": s.observation_id, "run_id": s.run_id, "observed_at": s.observed_at, "window_start": s.window_start, "window_end": s.window_end,
            "trend_score": s.trend_score, "score_coverage": s.score_coverage, "growth": s.growth, "momentum_pp": s.momentum_pp,
            "momentum_direction": s.momentum_direction, "novelty": s.novelty, "document_volume": s.document_volume, "sources": s.sources,
            "lifecycle": s.lifecycle, "formula_version": s.formula_version, "model_version": s.model_version}


# ------------------------------------------------------------------ events
def serialize_event(db: Session, e: TrendEvent, notif: Notification | None = None, docs: bool = True) -> dict:
    ev_docs = []
    if docs and e.evidence_document_ids:
        rows = db.execute(select(Document.id, Document.title, Document.url, Document.published_at).where(Document.id.in_([uuid.UUID(i) for i in e.evidence_document_ids]))).all()
        ev_docs = [{"document_id": str(i), "title": t, "url": u, "published_at": p} for i, t, u, p in rows]
    return {
        "id": str(e.id), "topic_id": str(e.topic_id) if e.topic_id else None, "topic_name": e.topic.name if e.topic else None, "event_type": e.event_type,
        "severity": e.severity, "title": e.title, "description": e.description, "previous_value": e.previous_value, "current_value": e.current_value,
        "change_percentage": e.change_percentage, "previous_observation_id": str(e.previous_observation_id) if e.previous_observation_id else None,
        "current_observation_id": str(e.current_observation_id) if e.current_observation_id else None, "evidence": ev_docs, "explanation": e.explanation,
        "details": e.details, "detection_version": e.detection_version, "state": e.state, "detected_at": e.detected_at,
        "has_evidence": bool(e.evidence_document_ids),
    }


def list_events(db: Session, *, event_type=None, severity=None, state=None, topic_id=None, date_from=None, date_to=None, limit=50, offset=0):
    q = select(TrendEvent)
    if event_type:
        q = q.where(TrendEvent.event_type == event_type)
    if severity:
        q = q.where(TrendEvent.severity == severity)
    if state:
        q = q.where(TrendEvent.state == state)
    if topic_id:
        q = q.where(TrendEvent.topic_id == _uuid(topic_id, "Trend"))
    if date_from:
        q = q.where(TrendEvent.detected_at >= date_from)
    if date_to:
        q = q.where(TrendEvent.detected_at <= date_to)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(TrendEvent.detected_at.desc(), TrendEvent.id).limit(limit).offset(offset)).all()
    return [serialize_event(db, e) for e in rows], total


def get_event(db: Session, event_id) -> TrendEvent:
    e = db.get(TrendEvent, _uuid(event_id, "Event"))
    if e is None:
        raise LookupError("Event not found")
    return e


def set_event_state(db: Session, event_id, state: str) -> dict:
    """Only the feed state changes. The event itself and its notification are untouched."""
    e = get_event(db, event_id)
    e.state, e.state_changed_at = state, _now()
    db.commit()
    return serialize_event(db, e)


# ------------------------------------------------------------------ notifications
def _notif_out(db: Session, n: Notification) -> dict:
    return {"id": str(n.id), "event_id": str(n.event_id), "severity": n.severity, "read": n.read_at is not None, "read_at": n.read_at,
            "dismissed": n.dismissed_at is not None, "created_at": n.created_at, "event": serialize_event(db, n.event, n, docs=False)}


def list_notifications(db: Session, *, status="unread", severity=None, limit=50, offset=0):
    q = select(Notification)
    if status == "unread":
        q = q.where(Notification.read_at.is_(None), Notification.dismissed_at.is_(None))
    elif status == "dismissed":
        q = q.where(Notification.dismissed_at.is_not(None))
    else:  # history: everything not dismissed, plus dismissed stay retrievable via status=dismissed
        q = q.where(Notification.dismissed_at.is_(None))
    if severity:
        q = q.where(Notification.severity == severity)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(Notification.created_at.desc(), Notification.id).limit(limit).offset(offset)).all()
    return [_notif_out(db, n) for n in rows], total


def unread_count(db: Session) -> dict:
    n = db.scalar(select(func.count()).select_from(Notification).where(Notification.read_at.is_(None), Notification.dismissed_at.is_(None))) or 0
    by = dict(db.execute(select(Notification.severity, func.count()).where(Notification.read_at.is_(None), Notification.dismissed_at.is_(None)).group_by(Notification.severity)).all())
    return {"unread": n, "by_severity": by}


def patch_notification(db: Session, notification_id, read: bool | None, dismissed: bool | None) -> dict:
    n = db.get(Notification, _uuid(notification_id, "Notification"))
    if n is None:
        raise LookupError("Notification not found")
    now = _now()
    if read is not None:
        n.read_at = (n.read_at or now) if read else None
    if dismissed is not None:
        n.dismissed_at = (n.dismissed_at or now) if dismissed else None
        if dismissed and n.read_at is None:
            n.read_at = now
    db.commit()
    return _notif_out(db, n)


def mark_all_read(db: Session) -> dict:
    res = db.execute(update(Notification).where(Notification.read_at.is_(None), Notification.dismissed_at.is_(None)).values(read_at=_now()))
    db.commit()
    return {"marked": res.rowcount}


# ------------------------------------------------------------------ preferences
def preferences_out(p: MonitoringPreference) -> dict:
    return {"min_notification_severity": p.min_notification_severity, "muted_event_types": p.muted_event_types or [], "notify_watchlist_only": p.notify_watchlist_only}


def get_preferences(db: Session) -> dict:
    return preferences_out(pipeline.get_preferences(db))


def set_preferences(db: Session, min_sev: str, muted: list[str], wl_only: bool) -> dict:
    from app.models.monitoring import EVENT_TYPES

    bad = [m for m in muted if m not in EVENT_TYPES]
    if bad:
        raise ValueError(f"Unknown event type(s): {', '.join(bad)}")
    p = pipeline.get_preferences(db)
    p.min_notification_severity, p.muted_event_types, p.notify_watchlist_only = min_sev, sorted(set(muted)), wl_only
    db.commit()
    return preferences_out(p)


# ------------------------------------------------------------------ watchlist
def _latest_event(db: Session, topic_id) -> dict | None:
    e = db.scalar(select(TrendEvent).where(TrendEvent.topic_id == topic_id).order_by(TrendEvent.detected_at.desc()).limit(1))
    return None if e is None else {"id": str(e.id), "event_type": e.event_type, "severity": e.severity, "title": e.title, "detected_at": e.detected_at, "state": e.state}


def _watch_row(db: Session, w: TrendWatchlist, fresh: _Freshness) -> dict:
    hist = load_snapshots(db, w.topic_id, 30)
    cur = hist[-1] if hist else None
    prev, change, note = (hist[-2] if len(hist) > 1 else None), None, None
    if cur and prev:
        ok, why = comparable(prev, cur, get_settings().monitoring_window_tolerance_days)
        if ok and cur.trend_score is not None and prev.trend_score is not None:
            change = round(cur.trend_score - prev.trend_score, 1)
        elif not ok:
            note = why
    t = w.topic
    last = t.last_observed_at or (cur.observed_at if cur else None)
    return {
        "topic_id": str(t.id), "topic_name": t.name, "monitoring_enabled": w.monitoring_enabled, "priority": w.priority, "user_note": w.user_note,
        "added_at": w.added_at, "last_viewed_at": w.last_viewed_at, "latest_score": cur.trend_score if cur else None, "previous_score": prev.trend_score if prev else None,
        "score_change": change, "score_change_note": note, "growth": cur.growth if cur else None, "momentum_pp": cur.momentum_pp if cur else None,
        "momentum_direction": cur.momentum_direction if cur else None, "lifecycle": cur.lifecycle if cur else None,
        "activity_state": fresh.state(last), "document_volume": cur.document_volume if cur else None, "last_observation_at": cur.observed_at if cur else None,
        "latest_event": _latest_event(db, t.id), "observations": len(hist),
    }


def add_to_watchlist(db: Session, topic_id: str, priority: str = "normal", note: str = "") -> tuple[dict, bool]:
    topic = db.get(Topic, _uuid(topic_id, "Trend"))
    if topic is None:
        raise LookupError("Trend not found")
    new_id = db.execute(
        pg_insert(TrendWatchlist).values(id=uuid.uuid4(), topic_id=topic.id, priority=priority, user_note=note)
        .on_conflict_do_nothing(index_elements=["topic_id"], index_where=TrendWatchlist.user_id.is_(None)).returning(TrendWatchlist.id)
    ).scalar()
    db.commit()
    w = db.scalar(select(TrendWatchlist).where(TrendWatchlist.topic_id == topic.id, TrendWatchlist.user_id.is_(None)))
    return _watch_row(db, w, _Freshness(db)), new_id is not None


def _get_watch(db: Session, topic_id) -> TrendWatchlist:
    w = db.scalar(select(TrendWatchlist).where(TrendWatchlist.topic_id == _uuid(topic_id, "Trend"), TrendWatchlist.user_id.is_(None)))
    if w is None:
        raise LookupError("Trend is not on the watchlist")
    return w


def patch_watch(db: Session, topic_id, **fields) -> dict:
    w = _get_watch(db, topic_id)
    for k, v in fields.items():
        if v is not None:
            setattr(w, k, v)
    db.commit()
    return _watch_row(db, w, _Freshness(db))


def remove_watch(db: Session, topic_id) -> None:
    """Unfollowing removes only the watchlist entry; observations and past events are kept."""
    db.delete(_get_watch(db, topic_id))
    db.commit()


def list_watchlist(db: Session, *, q=None, lifecycle=None, activity=None, priority=None, enabled=None, sort="priority", limit=50, offset=0):
    fresh = _Freshness(db)
    rows = [_watch_row(db, w, fresh) for w in db.scalars(select(TrendWatchlist).where(TrendWatchlist.user_id.is_(None)))]
    if q:
        rows = [r for r in rows if q.lower() in r["topic_name"].lower()]
    if lifecycle:
        rows = [r for r in rows if r["lifecycle"] == lifecycle]
    if activity:
        rows = [r for r in rows if r["activity_state"] == activity]
    if priority:
        rows = [r for r in rows if r["priority"] == priority]
    if enabled is not None:
        rows = [r for r in rows if r["monitoring_enabled"] == enabled]
    pri = {"high": 0, "normal": 1, "low": 2}
    keys = {
        "priority": lambda r: (pri[r["priority"]], r["topic_name"].lower()),
        "name": lambda r: r["topic_name"].lower(),
        "score": lambda r: -(r["latest_score"] if r["latest_score"] is not None else -1),
        "change": lambda r: -(r["score_change"] if r["score_change"] is not None else -1e9),
        "recent": lambda r: -(r["last_observation_at"].timestamp() if r["last_observation_at"] else 0),
    }
    rows.sort(key=keys.get(sort, keys["priority"]))
    return rows[offset: offset + limit], len(rows)


def trend_monitoring(db: Session, topic_id, mark_viewed: bool = True) -> dict:
    t = db.get(Topic, _uuid(topic_id, "Trend"))
    if t is None:
        raise LookupError("Trend not found")
    w = db.scalar(select(TrendWatchlist).where(TrendWatchlist.topic_id == t.id, TrendWatchlist.user_id.is_(None)))
    fresh = _Freshness(db)
    hist = load_snapshots(db, t.id, 200)
    cur = hist[-1] if hist else None
    if w is not None and mark_viewed:
        w.last_viewed_at = _now()
        db.commit()
    dossier = db.scalar(select(ResearchDossier).where(ResearchDossier.topic_id == t.id).order_by(ResearchDossier.updated_at.desc()).limit(1))
    events, total = list_events(db, topic_id=str(t.id), limit=20)
    last = t.last_observed_at or (cur.observed_at if cur else None)
    return {
        "topic_id": str(t.id), "topic_name": t.name, "terms": (t.terms or [])[:8], "followed": w is not None,
        "watch": None if w is None else {"monitoring_enabled": w.monitoring_enabled, "priority": w.priority, "user_note": w.user_note, "added_at": w.added_at, "last_viewed_at": w.last_viewed_at},
        "activity_state": fresh.state(last), "latest": _snap(cur), "observation_count": len(hist), "events": events, "event_total": total,
        "dossier": None if dossier is None else {"id": str(dossier.id), "status": dossier.status, "generated_at": dossier.generated_at, "has_content": dossier.generated_at is not None},
    }


def trend_history(db: Session, topic_id, limit: int = 200) -> list[dict]:
    t = db.get(Topic, _uuid(topic_id, "Trend"))
    if t is None:
        raise LookupError("Trend not found")
    hist = load_snapshots(db, t.id, limit)
    out, prev = [], None
    for s in hist:
        d = _snap(s)
        d["lifecycle_changed"] = bool(prev and prev.lifecycle and s.lifecycle and prev.lifecycle != s.lifecycle)
        d["comparable_with_previous"] = None if prev is None else comparable(prev, s, get_settings().monitoring_window_tolerance_days)[0]
        out.append(d)
        prev = s
    return out


# ------------------------------------------------------------------ overview + status
def _job_row(r: MonitoringJobRun | None) -> dict | None:
    return None if r is None else {"id": str(r.id), "job_type": r.job_type, "status": r.status, "trigger": r.trigger, "started_at": r.started_at,
                                   "completed_at": r.completed_at, "duration_ms": r.duration_ms, "error": r.error_message, "attempt": r.attempt}


def monitoring_status(db: Session) -> dict:
    from app.monitoring import jobs

    s = get_settings()

    def last(job: str, status: str | None = "completed"):
        q = select(MonitoringJobRun).where(MonitoringJobRun.job_type == job)
        if status:
            q = q.where(MonitoringJobRun.status == status)
        return db.scalar(q.order_by(MonitoringJobRun.started_at.desc()).limit(1))

    sched = jobs.scheduler
    running = db.scalar(select(func.count()).select_from(MonitoringJobRun).where(MonitoringJobRun.status == "running")) or 0
    run = pipeline.latest_completed_run(db)
    failures = db.scalars(select(MonitoringJobRun).where(MonitoringJobRun.status == "failed").order_by(MonitoringJobRun.started_at.desc()).limit(5)).all()
    return {
        "scheduler": {"enabled": s.monitoring_scheduler_enabled, "state": ("disabled" if not s.monitoring_scheduler_enabled else "running_cycle" if running or (sched and sched.running_cycle) else "idle" if sched else "not_started"),
                      "interval_minutes": s.monitoring_interval_minutes, "next_scheduled_at": jobs.next_due(None, sched.started_at if sched else None) if s.monitoring_scheduler_enabled else None},
        "last_successful": {j: _job_row(last(j)) for j in ("collection", "recompute", "detection", "evidence", "notifications", "cycle")},
        "last_cycle": _job_row(last("cycle", None)),
        "latest_failures": [_job_row(f) for f in failures],
        "monitored_trends": db.scalar(select(func.count()).select_from(TrendWatchlist).where(TrendWatchlist.monitoring_enabled.is_(True))) or 0,
        "latest_trend_run_completed_at": run.completed_at if run else None,
    }


def overview(db: Session) -> dict:
    rows, total = list_watchlist(db, limit=500)
    since = _now() - timedelta(days=7)
    new = db.scalar(select(func.count()).select_from(TrendEvent).where(TrendEvent.state == "new")) or 0
    important = db.scalar(select(func.count()).select_from(TrendEvent).where(TrendEvent.severity.in_(("important", "critical")), TrendEvent.detected_at >= since, TrendEvent.state != "dismissed")) or 0
    gaining = [r for r in rows if r["monitoring_enabled"] and (r["growth"] or 0) > 0 and r["momentum_direction"] == "accelerating"]
    declining = [r for r in rows if r["monitoring_enabled"] and ((r["score_change"] or 0) < 0 or r["momentum_direction"] == "decelerating")]
    st = monitoring_status(db)
    run = pipeline.latest_completed_run(db)
    return {
        "followed": total, "active_monitored": sum(1 for r in rows if r["monitoring_enabled"] and r["activity_state"] == "active"),
        "new_events": new, "important_events_7d": important, "gaining_momentum": gaining[:5], "declining": declining[:5],
        "latest_cycle": st["last_cycle"], "data_freshness": {"latest_trend_run_completed_at": run.completed_at if run else None},
        "unread_notifications": unread_count(db)["unread"],
    }
