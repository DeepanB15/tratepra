from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import ResearchQuery, ResearchResult


def list_history(db: Session, limit: int = 100) -> list[dict]:
    rows = db.scalars(
        select(ResearchQuery).options(joinedload(ResearchQuery.result)).order_by(ResearchQuery.created_at.desc()).limit(limit)
    ).unique()
    return [
        {
            "research_id": str(q.result.id) if q.result else str(q.id),
            "query": q.query,
            "sources": q.sources,
            "created_at": q.created_at,
        }
        for q in rows
        if q.result is not None
    ]
