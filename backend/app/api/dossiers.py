"""Research dossier endpoints. Generation runs in the background; clients poll GET /{id} for `processing.status`."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ResearchDossier
from app.research.query_processor import InvalidQuery
from app.schemas import DossierClaimOut, DossierCreate, DossierEvidenceOut, DossierListItem, DossierOut
from app.services import dossier_service as svc

router = APIRouter()
Role = Literal["supporting", "contradictory", "context"]
ClaimStatus = Literal["supported", "partially_supported", "contradicted", "unverified", "insufficient_evidence"]


def _404(exc: Exception):
    raise HTTPException(status_code=404, detail=str(exc) or "Not found")


@router.post("", response_model=DossierOut, status_code=202)
def create(req: DossierCreate, response: Response, db: Session = Depends(get_db)):
    """202 when generation was started; 200 with the existing dossier when it already exists and nothing needs to run."""
    try:
        dossier, created = svc.create_dossier(db, topic_id=req.topic_id, query=req.query, time_range=req.time_range, sources=req.sources)
    except LookupError as exc:
        _404(exc)
    except InvalidQuery as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    started = False
    if created or dossier.status in ("pending", "failed"):
        started = svc.claim_run(db, dossier.id)
        if started:
            svc.dispatch(dossier.id, refresh=req.refresh_articles)
    db.expire_all()
    if not (created or started):
        response.status_code = 200
    out = svc.serialize(db, svc.get_dossier(db, dossier.id))
    out["created"] = created
    return out


@router.get("", response_model=list[DossierListItem])
def list_dossiers(
    response: Response,
    topic_id: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = select(ResearchDossier)
    if topic_id:
        q = q.where(ResearchDossier.topic_id == topic_id)
    from sqlalchemy import func

    response.headers["X-Total-Count"] = str(db.scalar(select(func.count()).select_from(q.subquery())) or 0)
    rows = db.scalars(q.order_by(ResearchDossier.updated_at.desc()).limit(limit).offset(offset)).all()
    return [
        {"id": str(d.id), "topic_id": str(d.topic_id) if d.topic_id else None, "title": d.title, "status": d.status,
         "generated_at": d.generated_at, "time_range": d.time_range}
        for d in rows
    ]


@router.get("/{dossier_id}", response_model=DossierOut)
def get(dossier_id: str, db: Session = Depends(get_db)):
    try:
        return svc.serialize(db, svc.get_dossier(db, dossier_id))
    except LookupError as exc:
        _404(exc)


@router.get("/{dossier_id}/evidence", response_model=list[DossierEvidenceOut])
def evidence(
    dossier_id: str,
    response: Response,
    role: Role | None = None,
    publisher: str | None = Query(default=None, max_length=100),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        items, total = svc.list_evidence(db, dossier_id, role=role, publisher=publisher, date_from=date_from, date_to=date_to, limit=limit, offset=offset)
    except LookupError as exc:
        _404(exc)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get("/{dossier_id}/claims", response_model=list[DossierClaimOut])
def claims(
    dossier_id: str,
    response: Response,
    status: ClaimStatus | None = None,
    section: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    try:
        items, total = svc.list_claims(db, dossier_id, status=status, section=section, limit=limit, offset=offset)
    except LookupError as exc:
        _404(exc)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.post("/{dossier_id}/refresh", response_model=DossierOut, status_code=202)
def refresh(dossier_id: str, db: Session = Depends(get_db)):
    """Regenerate. The previous result stays available until the new one completes; 409 if one is already running."""
    try:
        d = svc.get_dossier(db, dossier_id)
    except LookupError as exc:
        _404(exc)
    if not svc.claim_run(db, d.id):
        raise HTTPException(status_code=409, detail="A generation is already in progress for this dossier")
    svc.dispatch(d.id, refresh=True)
    db.expire_all()
    return svc.serialize(db, svc.get_dossier(db, d.id))
