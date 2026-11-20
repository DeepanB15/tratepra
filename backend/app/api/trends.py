from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import TrendDetail, TrendHistoryPoint, TrendSummary
from app.services import trend_service

router = APIRouter()


@router.get("", response_model=list[TrendSummary])
def list_trends(
    lifecycle: str | None = None,
    q: str | None = None,
    min_sources: int | None = None,
    db: Session = Depends(get_db),
):
    return trend_service.list_trends(db, lifecycle=lifecycle, q=q, min_sources=min_sources)


@router.get("/{topic_id}", response_model=TrendDetail)
def detail(topic_id: str, db: Session = Depends(get_db)):
    try:
        return trend_service.trend_detail(db, topic_id)
    except (LookupError, ValueError):
        raise HTTPException(status_code=404, detail="Trend not found")


@router.get("/{topic_id}/history", response_model=list[TrendHistoryPoint])
def history(topic_id: str, db: Session = Depends(get_db)):
    try:
        return trend_service.trend_history(db, topic_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Trend not found")
