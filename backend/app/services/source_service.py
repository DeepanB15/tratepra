from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors import all_connectors
from app.core.database import SessionLocal
from app.models import CollectionLog, Document, Source

SOURCE_QUALITY = {"google_news": 80.0, "youtube": 65.0, "reddit": 55.0, "google_trends": 70.0}
FAILING = {"error", "quota", "rate_limit", "auth"}


def derive_state(configured: bool, last_status: str | None) -> str:
    """Operational state from facts, never from configuration alone.

    unavailable  - not configured (missing credentials / access)
    configured   - configured but no successful run yet (unverified)
    operational  - the last run succeeded
    failing      - the last run failed (error, quota, rate limit, auth)
    """
    if not configured:
        return "unavailable"
    if last_status == "ok":
        return "operational"
    if last_status in FAILING:
        return "failing"
    return "configured"


def ensure_sources() -> None:
    with SessionLocal() as db:
        existing = {s.key for s in db.scalars(select(Source))}
        for c in all_connectors():
            if c.key not in existing:
                db.add(Source(key=c.key, name=c.name, quality_weight=SOURCE_QUALITY.get(c.key, 60.0)))
        db.commit()


def source_availability(db: Session) -> list[dict]:
    rows = {s.key: s for s in db.scalars(select(Source))}
    doc_stats = {
        key: (count, latest)
        for key, count, latest in db.execute(
            select(Source.key, func.count(Document.id), func.max(func.coalesce(Document.published_at, Document.collected_at)))
            .join(Document, Document.source_id == Source.id, isouter=True)
            .group_by(Source.key)
        )
    }
    last_log = {}
    for log in db.scalars(select(CollectionLog).order_by(CollectionLog.created_at.desc()).limit(200)):
        last_log.setdefault(log.source_key, log)

    out = []
    for c in all_connectors():
        a = c.availability()
        s = rows.get(c.key)
        status = s.last_status if s else None
        count, latest = doc_stats.get(c.key, (0, None))
        log = last_log.get(c.key)
        a.update(
            {
                "state": derive_state(a["available"], status),
                "last_status": status,
                "last_error": s.last_error if s else None,
                "last_run_at": s.last_run_at if s else None,
                "document_count": count,
                "latest_document_at": latest,
                "last_fetched": log.fetched if log else None,
                "last_accepted": log.inserted if log else None,
                "last_duration_ms": log.duration_ms if log else None,
            }
        )
        out.append(a)
    return out


def recent_logs(db: Session, limit: int = 50) -> list[dict]:
    logs = db.scalars(select(CollectionLog).order_by(CollectionLog.created_at.desc()).limit(limit)).all()
    return [
        {
            "run_id": l.run_id,
            "source": l.source_key,
            "query": l.query,
            "status": l.status,
            "fetched": l.fetched,
            "accepted": l.inserted,
            "duplicates": l.duplicates,
            "out_of_window": l.out_of_window,
            "undated": l.undated,
            "rejected": l.rejected,
            "error": l.error,
            "duration_ms": l.duration_ms,
            "started_at": l.started_at,
            "completed_at": l.completed_at,
            "created_at": l.created_at,
        }
        for l in logs
    ]
