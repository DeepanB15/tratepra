from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import require_internal_token
from app.ingestion.collector import collect
from app.ingestion.embedding_store import embed_pending
from app.services import source_service, trend_service

router = APIRouter(dependencies=[Depends(require_internal_token)])


class CollectRequest(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=20)
    sources: list[str] | None = Field(default=None, max_length=4)
    time_range: str = Field(default="30d", pattern=r"^\d+[dhw]$")


@router.post("/collection/run")
def run_collection(body: CollectRequest, db: Session = Depends(get_db)):
    results = {q: collect(db, q, body.sources, body.time_range) for q in body.queries}
    embedded = embed_pending(db)
    return {"results": results, "embedded": embedded}


@router.get("/collection/status")
def collection_status(db: Session = Depends(get_db)):
    return source_service.recent_logs(db, 50)


@router.post("/trends/recompute")
def recompute(db: Session = Depends(get_db)):
    embed_pending(db)
    return trend_service.recompute(db)
