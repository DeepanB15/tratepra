from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import DiscoveryOverview, RunDetail, RunSummary, TrendDetail, TrendHistoryPoint, TrendSummary
from app.services import trend_service

router = APIRouter()

Lifecycle = Literal["emerging", "growing", "peaking", "declining"]
ActivityState = Literal["active", "stale", "inactive", "all"]
Momentum = Literal["accelerating", "decelerating", "steady", "unknown"]
SortKey = Literal["score", "growth", "momentum", "documents", "recent", "name"]
RunStatus = Literal["pending", "running", "completed", "failed"]


@router.get("", response_model=list[TrendSummary])
def list_trends(
    response: Response,
    q: str | None = Query(default=None, max_length=100, description="Match against topic name or terms"),
    lifecycle: Lifecycle | None = None,
    activity_state: ActivityState = Query(default="active", description="Operational state; 'all' disables the filter. Default hides stale/inactive topics."),
    min_sources: int | None = Query(default=None, ge=1, le=20),
    min_score: float | None = Query(default=None, ge=0, le=100),
    max_age_days: float | None = Query(default=None, gt=0, le=3650, description="Last observed at most this many days before the latest completed run"),
    momentum: Momentum | None = None,
    is_new: bool | None = None,
    score_withheld: bool | None = None,
    sort: SortKey = "score",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Array body (unchanged shape). Pagination totals are returned in X-Total-Count / X-Limit / X-Offset."""
    items, total = trend_service.search_trends(
        db, lifecycle=lifecycle, q=q, min_sources=min_sources, min_score=min_score,
        activity_state=None if activity_state == "all" else activity_state, max_age_days=max_age_days,
        momentum_direction=momentum, is_new=is_new, score_withheld=score_withheld, sort=sort, order=order, limit=limit, offset=offset,
    )
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    return items


# Static routes must be declared before "/{topic_id}".
@router.get("/overview", response_model=DiscoveryOverview)
def overview(db: Session = Depends(get_db)):
    return trend_service.discovery_overview(db)


@router.get("/runs", response_model=list[RunSummary])
def runs(
    response: Response,
    status: RunStatus | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Read-only run diagnostics. Error text is scrubbed of credentials; configuration holds model parameters only."""
    items, total = trend_service.list_runs(db, limit=limit, offset=offset, status=status)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/runs/{run_id}", response_model=RunDetail)
def run_detail(run_id: str, db: Session = Depends(get_db)):
    try:
        return trend_service.get_run(db, run_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Run not found")


@router.get("/{topic_id}", response_model=TrendDetail)
def detail(topic_id: str, db: Session = Depends(get_db)):
    try:
        return trend_service.trend_detail(db, topic_id)
    except (LookupError, ValueError):
        raise HTTPException(status_code=404, detail="Trend not found")


@router.get("/{topic_id}/history", response_model=list[TrendHistoryPoint])
def history(topic_id: str, limit: int = Query(default=200, ge=1, le=1000), db: Session = Depends(get_db)):
    try:
        return trend_service.trend_history(db, topic_id, limit=limit)
    except (LookupError, ValueError):
        raise HTTPException(status_code=404, detail="Trend not found")
