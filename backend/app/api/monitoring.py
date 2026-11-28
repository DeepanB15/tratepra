"""Monitoring API (single-user; no authentication exists in this app). Job triggers live under /api/internal."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import EventPatch, NotificationPatch, PreferencesIn, WatchlistAdd, WatchlistPatch
from app.services import monitoring_service as svc

router = APIRouter()
EventType = Literal["growth_acceleration", "growth_slowdown", "activity_decline", "lifecycle_transition", "new_supporting_evidence", "contradictory_evidence",
                    "new_related_topic", "activity_disappearance", "activity_spike", "new_emerging_trend", "monitoring_failure"]
Severity = Literal["informational", "important", "critical"]


def nf(exc: Exception):
    raise HTTPException(status_code=404, detail=str(exc))


# --- overview / status (static routes first)
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    return svc.overview(db)


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return svc.monitoring_status(db)


@router.get("/preferences")
def get_prefs(db: Session = Depends(get_db)):
    return svc.get_preferences(db)


@router.put("/preferences")
def put_prefs(body: PreferencesIn, db: Session = Depends(get_db)):
    try:
        return svc.set_preferences(db, body.min_notification_severity, body.muted_event_types, body.notify_watchlist_only)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# --- watchlist
@router.get("/watchlist")
def watchlist(response: Response, q: str | None = Query(default=None, max_length=100), lifecycle: str | None = Query(default=None, max_length=20),
              activity: Literal["active", "stale", "inactive"] | None = None, priority: Literal["low", "normal", "high"] | None = None,
              enabled: bool | None = None, sort: Literal["priority", "name", "score", "change", "recent"] = "priority",
              limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    rows, total = svc.list_watchlist(db, q=q, lifecycle=lifecycle, activity=activity, priority=priority, enabled=enabled, sort=sort, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.post("/watchlist", status_code=201)
def follow(body: WatchlistAdd, response: Response, db: Session = Depends(get_db)):
    try:
        row, created = svc.add_to_watchlist(db, body.topic_id, body.priority, body.user_note)
    except LookupError as exc:
        nf(exc)
    if not created:
        response.status_code = 200  # already followed: idempotent
    return row


@router.patch("/watchlist/{topic_id}")
def patch_watch(topic_id: str, body: WatchlistPatch, db: Session = Depends(get_db)):
    try:
        return svc.patch_watch(db, topic_id, monitoring_enabled=body.monitoring_enabled, priority=body.priority, user_note=body.user_note)
    except LookupError as exc:
        nf(exc)


@router.delete("/watchlist/{topic_id}")
def unfollow(topic_id: str, db: Session = Depends(get_db)):
    try:
        svc.remove_watch(db, topic_id)
    except LookupError as exc:
        nf(exc)
    return {"deleted": True}


# --- trend monitoring
@router.get("/trends/{topic_id}")
def trend(topic_id: str, db: Session = Depends(get_db)):
    try:
        return svc.trend_monitoring(db, topic_id)
    except LookupError as exc:
        nf(exc)


@router.get("/trends/{topic_id}/history")
def trend_history(topic_id: str, limit: int = Query(default=200, ge=1, le=500), db: Session = Depends(get_db)):
    try:
        return svc.trend_history(db, topic_id, limit)
    except LookupError as exc:
        nf(exc)


@router.get("/trends/{topic_id}/events")
def trend_events(topic_id: str, response: Response, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    try:
        rows, total = svc.list_events(db, topic_id=topic_id, limit=limit, offset=offset)
    except LookupError as exc:
        nf(exc)
    response.headers["X-Total-Count"] = str(total)
    return rows


# --- events
@router.get("/events")
def events(response: Response, event_type: EventType | None = None, severity: Severity | None = None, state: Literal["new", "read", "dismissed", "archived"] | None = None,
           topic_id: str | None = Query(default=None, max_length=64), date_from: datetime | None = None, date_to: datetime | None = None,
           limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    try:
        rows, total = svc.list_events(db, event_type=event_type, severity=severity, state=state, topic_id=topic_id, date_from=date_from, date_to=date_to, limit=limit, offset=offset)
    except LookupError as exc:
        nf(exc)
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/events/{event_id}")
def event(event_id: str, db: Session = Depends(get_db)):
    try:
        return svc.serialize_event(db, svc.get_event(db, event_id))
    except LookupError as exc:
        nf(exc)


@router.patch("/events/{event_id}")
def patch_event(event_id: str, body: EventPatch, db: Session = Depends(get_db)):
    try:
        return svc.set_event_state(db, event_id, body.state)
    except LookupError as exc:
        nf(exc)


# --- notifications
@router.get("/notifications")
def notifications(response: Response, status: Literal["unread", "all", "dismissed"] = "unread", severity: Severity | None = None,
                  limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    rows, total = svc.list_notifications(db, status=status, severity=severity, limit=limit, offset=offset)
    response.headers["X-Total-Count"] = str(total)
    return rows


@router.get("/notifications/unread-count")
def unread(db: Session = Depends(get_db)):
    return svc.unread_count(db)


@router.post("/notifications/mark-all-read")
def mark_all(db: Session = Depends(get_db)):
    return svc.mark_all_read(db)


@router.patch("/notifications/{notification_id}")
def patch_notification(notification_id: str, body: NotificationPatch, db: Session = Depends(get_db)):
    try:
        return svc.patch_notification(db, notification_id, body.read, body.dismissed)
    except LookupError as exc:
        nf(exc)
