import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ResearchResult, SavedItem, Topic


def save_item(db: Session, item_type: str, item_id: str, title: str = "") -> SavedItem:
    iid = uuid.UUID(item_id)
    existing = db.scalar(select(SavedItem).where(SavedItem.item_type == item_type, SavedItem.item_id == iid))
    if existing:
        return existing
    if not title:
        if item_type == "trend":
            t = db.get(Topic, iid)
            title = t.name if t else ""
        else:
            r = db.get(ResearchResult, iid)
            title = r.query.query if r else ""
    item = SavedItem(item_type=item_type, item_id=iid, title=title)
    db.add(item)
    db.commit()
    return item


def list_saved(db: Session) -> list[SavedItem]:
    return list(db.scalars(select(SavedItem).order_by(SavedItem.created_at.desc())))


def delete_saved(db: Session, saved_id: str) -> bool:
    item = db.get(SavedItem, uuid.UUID(saved_id))
    if not item:
        return False
    db.delete(item)
    db.commit()
    return True
