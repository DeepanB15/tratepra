from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import source_service

router = APIRouter()


@router.get("")
def sources(db: Session = Depends(get_db)):
    """Connector availability, so the UI can show which sources are usable and why not."""
    return source_service.source_availability(db)


@router.get("/logs")
def logs(limit: int = 50, db: Session = Depends(get_db)):
    """Recent per-source collection runs (fetched / accepted / duplicates / failures)."""
    return source_service.recent_logs(db, min(max(limit, 1), 200))
