from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.research.query_processor import InvalidQuery
from app.schemas import HistoryItem, ResearchRequest, ResearchResponse
from app.services import history_service, research_service

router = APIRouter()


@router.post("/search", response_model=ResearchResponse)
def search(req: ResearchRequest, db: Session = Depends(get_db)):
    try:
        return research_service.run_research(db, req.query, req.sources, req.time_range, req.refresh)
    except InvalidQuery as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# NOTE: declared before "/{research_id}" so "history" is not parsed as an id.
@router.get("/history", response_model=list[HistoryItem])
def history(db: Session = Depends(get_db)):
    return history_service.list_history(db)


@router.get("/{research_id}", response_model=ResearchResponse)
def get_research(research_id: str, db: Session = Depends(get_db)):
    try:
        return research_service.serialize_result(db, research_id)
    except (LookupError, ValueError):
        raise HTTPException(status_code=404, detail="Research result not found")
