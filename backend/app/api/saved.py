from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import SavedCreate, SavedOut
from app.services import saved_service

router = APIRouter()


def _out(i) -> dict:
    return {"id": str(i.id), "item_type": i.item_type, "item_id": str(i.item_id), "title": i.title, "created_at": i.created_at}


@router.post("", response_model=SavedOut)
def save(body: SavedCreate, db: Session = Depends(get_db)):
    try:
        return _out(saved_service.save_item(db, body.item_type, body.item_id, body.title))
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid item_id")


@router.get("", response_model=list[SavedOut])
def list_saved(db: Session = Depends(get_db)):
    return [_out(i) for i in saved_service.list_saved(db)]


@router.delete("/{saved_id}")
def delete(saved_id: str, db: Session = Depends(get_db)):
    try:
        ok = saved_service.delete_saved(db, saved_id)
    except ValueError:
        ok = False
    if not ok:
        raise HTTPException(status_code=404, detail="Saved item not found")
    return {"deleted": True}
