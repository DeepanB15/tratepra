from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import HistoryItem
from app.services import history_service

router = APIRouter()


@router.get("", response_model=list[HistoryItem])
def list_history(db: Session = Depends(get_db)):
    return history_service.list_history(db)
