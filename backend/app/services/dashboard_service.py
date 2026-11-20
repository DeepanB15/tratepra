from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, ResearchQuery, ResearchResult, Source, Topic, TrendObservation
from app.services import source_service, trend_service


def overview(db: Session) -> dict:
    """All metrics computed from stored data; nothing hardcoded."""
    query_count = db.scalar(select(func.count(ResearchQuery.id))) or 0
    doc_count = db.scalar(select(func.count(Document.id))) or 0
    sources_with_data = db.scalar(select(func.count(func.distinct(Document.source_id)))) or 0

    trends = trend_service.list_trends(db, limit=500)
    scored = [t["trend_score"] for t in trends if t["trend_score"] is not None]
    emerging = sum(1 for t in trends if t["lifecycle"] == "emerging")

    lifecycle = {k: 0 for k in ("emerging", "growing", "peaking", "declining")}
    unlabelled = 0
    for t in trends:
        if t["lifecycle"] in lifecycle:
            lifecycle[t["lifecycle"]] += 1
        else:
            unlabelled += 1

    recent_q = db.execute(
        select(ResearchQuery, ResearchResult.id)
        .join(ResearchResult, ResearchResult.query_id == ResearchQuery.id)
        .order_by(ResearchQuery.created_at.desc())
        .limit(6)
    ).all()
    sources = source_service.source_availability(db)
    logs = source_service.recent_logs(db, limit=5)
    return {
        "research_query_count": query_count,
        "emerging_trend_count": emerging,
        "sources_analyzed": sources_with_data,
        "document_count": doc_count,
        "active_topic_count": len(trends),
        "lifecycle_distribution": {**lifecycle, "unlabelled": unlabelled},
        "sources": sources,
        "recent_collections": logs,
        "average_trend_score": round(sum(scored) / len(scored), 2) if scored else None,
        "trending": trends[:5],
        "recent_activity": [
            {"research_id": str(rid), "query": q.query, "created_at": q.created_at, "sources": q.sources}
            for q, rid in recent_q
        ],
        "generated_at": datetime.now(timezone.utc),
    }
