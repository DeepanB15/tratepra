"""Research dossier orchestration: creation, safe background generation, refresh, serialization.

Guarantees
- Creating the same dossier twice returns the existing row (unique `dossier_key`, insert-on-conflict).
- Only one generation runs per dossier: `claim_run` is a single conditional UPDATE (a 'running' row older than
  the configured timeout is treated as crashed and may be reclaimed).
- No DB transaction is held during LLM inference or article fetching.
- Content (sections, evidence, claims) is replaced in ONE transaction only when generation succeeds; a failed
  refresh records the failure on the row and leaves the previous result intact.
"""
import hashlib
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.connectors import CONNECTOR_CLASSES
from app.connectors.base import parse_time_range
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.ingestion.article_refresh import refresh_articles, stale_embedding_count
from app.ingestion.collector import NON_TEXT_SOURCES
from app.ingestion.embedding_store import embed_pending
from app.models import (
    ClaimEvidence,
    DossierClaim,
    DossierEvidence,
    ResearchDossier,
    Topic,
    TopicDocument,
)
from app.research import synthesizer
from app.research.context_builder import build_context, select_evidence_explained
from app.research.diagnostics import retrieval_diagnostics
from app.research.dossier_engine import NO_EVIDENCE_TEXT, build_dossier
from app.research.query_processor import InvalidQuery, process_query
from app.research.ranker import rank
from app.research.retriever import retrieve
from app.services.trend_run_service import sanitize_error

log = logging.getLogger(__name__)
_executor: ThreadPoolExecutor | None = None


# ------------------------------------------------------------------ creation / claiming
def default_sources() -> list[str]:
    return [k for k in CONNECTOR_CLASSES if k not in NON_TEXT_SOURCES]


def make_key(topic_id: str | None, query: str, time_range: str, sources: list[str]) -> str:
    subject = f"topic:{topic_id}" if topic_id else "q:" + re.sub(r"\s+", " ", query.lower()).strip()
    raw = "|".join([subject, time_range, ",".join(sorted(set(sources)))])
    return hashlib.sha256(raw.encode()).hexdigest()


def _topic_query(topic: Topic) -> str:
    terms = [t for t in (topic.terms or []) if isinstance(t, str)][:5]
    return " ".join([topic.name] + [t for t in terms if t.lower() not in topic.name.lower()])


def create_dossier(
    db: Session, *, topic_id: str | None = None, query: str | None = None, time_range: str = "30d", sources: list[str] | None = None
) -> tuple[ResearchDossier, bool]:
    """Returns (dossier, created). Raises LookupError (unknown topic) or InvalidQuery."""
    topic = None
    if topic_id:
        try:
            topic = db.get(Topic, uuid.UUID(str(topic_id)))
        except ValueError:
            topic = None
        if topic is None:
            raise LookupError("Topic not found")
    if not topic and not (query or "").strip():
        raise InvalidQuery("Provide a topic_id or a query")
    text = (query or "").strip() or _topic_query(topic)
    process_query(text, time_range)  # validates searchability (raises InvalidQuery)
    valid = [s for s in dict.fromkeys(sources or []) if s in CONNECTOR_CLASSES and s not in NON_TEXT_SOURCES] or default_sources()
    key = make_key(str(topic.id) if topic else None, text, time_range, valid)
    stmt = (
        pg_insert(ResearchDossier)
        .values(
            id=uuid.uuid4(), dossier_key=key, topic_id=topic.id if topic else None,
            title=topic.name if topic else text[:200], query_text=text, time_range=time_range,
            source_filters=valid, status="pending",
        )
        .on_conflict_do_nothing(index_elements=["dossier_key"])
        .returning(ResearchDossier.id)
    )
    new_id = db.execute(stmt).scalar()
    db.commit()
    row = db.scalar(select(ResearchDossier).where(ResearchDossier.dossier_key == key))
    return row, new_id is not None


def claim_run(db: Session, dossier_id) -> bool:
    """Atomically move a dossier to 'running'. False when another generation is already in progress."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    stale = now - timedelta(minutes=s.dossier_running_timeout_minutes)
    res = db.execute(
        update(ResearchDossier)
        .where(
            ResearchDossier.id == dossier_id,
            (ResearchDossier.status != "running") | (ResearchDossier.started_at < stale) | (ResearchDossier.started_at.is_(None)),
        )
        .values(status="running", started_at=now, completed_at=None, error_message=None)
    )
    db.commit()
    return res.rowcount == 1


def dispatch(dossier_id, *, refresh: bool = False) -> None:
    s = get_settings()
    if s.dossier_inline_execution:
        generate(dossier_id, refresh_articles_first=refresh)
        return
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=max(1, s.dossier_workers), thread_name_prefix="dossier")
    _executor.submit(generate, dossier_id, refresh_articles_first=refresh)


def shutdown_workers() -> None:
    global _executor
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None


# ------------------------------------------------------------------ generation
def generate(dossier_id, *, refresh_articles_first: bool = False, factory=None, synth=None) -> None:
    """Runs one generation for a dossier already claimed ('running'). Never raises."""
    factory = factory or SessionLocal
    synth = synth or synthesizer.synthesize
    try:
        content, meta = _compute(dossier_id, refresh_articles_first, factory, synth)
        _persist(dossier_id, content, meta, factory)
    except Exception as exc:
        log.exception("Dossier generation failed")
        _mark_failed(dossier_id, exc, factory)


def _compute(dossier_id, refresh_first: bool, factory, synth):
    s = get_settings()
    t0 = datetime.now(timezone.utc)
    refresh_summary = None
    with factory() as db:
        d = db.get(ResearchDossier, dossier_id)
        if d is None:
            raise LookupError("dossier disappeared")
        subject, query_text, time_range, sources, topic_id = d.title or d.query_text, d.query_text, d.time_range, list(d.source_filters or []), d.topic_id
        topic_terms, topic_doc_ids = [], []
        if topic_id:
            topic = db.get(Topic, topic_id)
            topic_terms = [t for t in (topic.terms or []) if isinstance(t, str)][:10] if topic else []
            topic_doc_ids = list(db.scalars(select(TopicDocument.document_id).where(TopicDocument.topic_id == topic_id).limit(50)))
        pq = process_query(query_text, time_range, topic_ids=[str(topic_id)] if topic_id else None)
        window_days = max(parse_time_range(pq.time_range or time_range).total_seconds() / 86400.0, 1.0)

        def run_retrieval():
            cands = retrieve(
                db, pq.cleaned, sources, pq.time_range or time_range, limit=s.dossier_retrieval_limit,
                keywords=pq.keywords, phrases=pq.phrases, include_document_ids=topic_doc_ids or None,
            )
            ranked = rank(cands, pq.keywords, window_days, phrases=pq.phrases)
            chosen, rejections = select_evidence_explained(ranked, max_items=s.dossier_max_evidence)
            return cands, ranked, chosen, rejections

        candidates, ranked, selected, rejections = run_retrieval()
        if refresh_first and selected:
            ids = [i.candidate.document.id for i in selected]
            refresh_summary = refresh_articles(db, ids, s.dossier_article_refresh_max)
            if refresh_summary["changed_text"]:
                db.close()
                embed_pending(db)
                candidates, ranked, selected, rejections = run_retrieval()
        ctx = build_context(selected, pq.keywords + pq.phrases)
        for i in selected:  # load what building needs, then detach so no connection is held during inference
            _ = i.candidate.document.source.key
        diag = retrieval_diagnostics(candidates, ranked, selected, rejections, pq.entities)
        diag["processed_query"] = {
            "original": pq.original, "cleaned": pq.cleaned, "keywords": pq.keywords, "phrases": pq.phrases,
            "entities": pq.entities, "intent": pq.intent, "time_range": pq.time_range, "topic_ids": pq.topic_ids,
        }
        diag["stale_embeddings"] = stale_embedding_count(db)
        if refresh_summary:
            diag["article_refresh"] = refresh_summary
        db.expunge_all()
        db.rollback()

    # ---- no DB connection is held from here until persistence ----
    if not selected:
        overview, findings, model, degraded = NO_EVIDENCE_TEXT, [], "none", False
    else:
        try:
            r = synth(pq.cleaned, ctx.text, len(selected))
            overview, findings, model, degraded = r.answer, r.key_findings, r.model, r.degraded
        except Exception as exc:  # LLM failure never fails the dossier
            log.warning("synthesis failed: %s", exc)
            r = synthesizer._extractive_fallback(pq.cleaned, ctx.text, len(selected), type(exc).__name__)
            overview, findings, model, degraded = r.answer, r.key_findings, r.model, True

    entity_seeds = [(e, "query") for e in pq.entities] + [(t, "topic_terms") for t in topic_terms]
    content = build_dossier(
        subject=subject, selected=selected, excerpts=ctx.excerpts or [], overview=overview, key_findings=findings,
        model=model, degraded=degraded, window_days=window_days, requested_sources=sources,
        entity_seeds=entity_seeds, support_threshold=s.dossier_support_overlap,
    )
    content.versions.update({"model": model, "embedding_model": _embedding_model(), "rank_weights": [s.rank_w_semantic, s.rank_w_keyword, s.rank_w_freshness, s.rank_w_quality]})
    meta = {"diagnostics": diag, "model": model, "started": t0, "synthesis_degraded": degraded}
    return content, meta


def _embedding_model() -> str:
    try:
        from app.intelligence.embeddings import model_name

        return model_name()
    except Exception:
        return ""


def _persist(dossier_id, content, meta, factory) -> None:
    now = datetime.now(timezone.utc)
    with factory.begin() as db:
        d = db.scalar(select(ResearchDossier).where(ResearchDossier.id == dossier_id).with_for_update())
        if d is None:
            return
        db.execute(delete(DossierClaim).where(DossierClaim.dossier_id == d.id))
        db.execute(delete(DossierEvidence).where(DossierEvidence.dossier_id == d.id))
        db.flush()
        key_to_id = {}
        for r in content.evidence:
            row = DossierEvidence(
                dossier_id=d.id, document_id=r["document_id"], rank=r["rank"], role=r["role"], role_reason=r["role_reason"],
                relevance=r["relevance"], publisher=r["publisher"][:255],
                published_at=datetime.fromisoformat(r["published"]).replace(tzinfo=timezone.utc) if r["published"] else None,
                excerpt=r["excerpt"], excerpt_basis=r["excerpt_basis"], article_status=r["article_status"],
            )
            db.add(row)
            db.flush()
            key_to_id[r["key"]] = row.id
        for n, c in enumerate(content.claims, start=1):
            claim = DossierClaim(
                dossier_id=d.id, claim_no=n, section=c.section, text=c.text, claim_type=c.claim_type, status=c.status,
                explanation=c.explanation, overlap=c.overlap, source_coverage=c.source_coverage,
            )
            db.add(claim)
            db.flush()
            for link in c.links:
                if link.evidence_key in key_to_id:
                    db.add(ClaimEvidence(claim_id=claim.id, dossier_evidence_id=key_to_id[link.evidence_key], relation=link.relation, overlap=link.overlap))
        d.sections = content.sections
        d.evidence_quality = content.evidence_quality
        d.diagnostics = meta["diagnostics"]
        d.versions = content.versions
        d.model = meta["model"][:100]
        d.generation = (d.generation or 0) + 1
        d.generated_at = now
        d.completed_at = now
        d.status = "completed"
        d.error_message = None


def _mark_failed(dossier_id, exc, factory) -> None:
    try:
        with factory.begin() as db:
            db.execute(
                update(ResearchDossier)
                .where(ResearchDossier.id == dossier_id)
                .values(status="failed", error_message=sanitize_error(exc), completed_at=datetime.now(timezone.utc))
            )
    except Exception:
        log.exception("could not record dossier failure")


# ------------------------------------------------------------------ reading
def _uuid(value) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except ValueError:
        raise LookupError("Dossier not found")


def get_dossier(db: Session, dossier_id) -> ResearchDossier:
    d = db.get(ResearchDossier, _uuid(dossier_id))
    if d is None:
        raise LookupError("Dossier not found")
    return d


def serialize(db: Session, d: ResearchDossier) -> dict:
    ev = db.scalar(select(func.count()).select_from(DossierEvidence).where(DossierEvidence.dossier_id == d.id)) or 0
    cl = db.scalar(select(func.count()).select_from(DossierClaim).where(DossierClaim.dossier_id == d.id)) or 0
    s = get_settings()
    stale_running = bool(d.status == "running" and d.started_at and d.started_at < datetime.now(timezone.utc) - timedelta(minutes=s.dossier_running_timeout_minutes))
    return {
        "id": str(d.id), "topic_id": str(d.topic_id) if d.topic_id else None, "title": d.title, "query": d.query_text,
        "time_range": d.time_range, "sources": d.source_filters or [],
        "processing": {
            "status": d.status, "error": d.error_message, "started_at": d.started_at, "completed_at": d.completed_at,
            "interrupted": stale_running, "has_content": d.generated_at is not None,
        },
        "generated_at": d.generated_at, "generation": d.generation, "model": d.model,
        "sections": d.sections or {}, "evidence_quality": d.evidence_quality or {}, "diagnostics": d.diagnostics or {},
        "versions": d.versions or {}, "evidence_count": ev, "claim_count": cl, "created_at": d.created_at,
        "limitations": [
            "Claim support is a lexical-overlap check against cited excerpts, not factual verification.",
            "Contradiction detection is a polarity-cue heuristic and will miss contradictions without explicit cues.",
            "Evidence quality labels describe retrieved evidence, not the probability that the dossier is correct.",
        ],
    }


def list_evidence(db: Session, dossier_id, *, role=None, publisher=None, date_from=None, date_to=None, limit=50, offset=0):
    d = get_dossier(db, dossier_id)
    q = select(DossierEvidence).where(DossierEvidence.dossier_id == d.id)
    if role:
        q = q.where(DossierEvidence.role == role)
    if publisher:
        q = q.where(DossierEvidence.publisher.ilike(f"%{publisher}%"))
    if date_from:
        q = q.where(DossierEvidence.published_at >= date_from)
    if date_to:
        q = q.where(DossierEvidence.published_at <= date_to)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(DossierEvidence.rank).limit(limit).offset(offset)).all()
    items = [
        {
            "id": str(r.id), "document_id": str(r.document_id), "rank": r.rank, "role": r.role, "role_reason": r.role_reason,
            "relevance": r.relevance, "title": r.document.title, "url": r.document.url, "publisher": r.publisher,
            "source": r.document.source.key, "published_at": r.published_at, "excerpt": r.excerpt, "excerpt_basis": r.excerpt_basis,
            "article_status": r.article_status,
        }
        for r in rows
    ]
    return items, total


def list_claims(db: Session, dossier_id, *, status=None, section=None, limit=50, offset=0):
    d = get_dossier(db, dossier_id)
    q = select(DossierClaim).where(DossierClaim.dossier_id == d.id)
    if status:
        q = q.where(DossierClaim.status == status)
    if section:
        q = q.where(DossierClaim.section == section)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.scalars(q.order_by(DossierClaim.claim_no).limit(limit).offset(offset)).all()
    items = []
    for c in rows:
        items.append(
            {
                "id": str(c.id), "claim_no": c.claim_no, "section": c.section, "text": c.text, "claim_type": c.claim_type,
                "status": c.status, "explanation": c.explanation, "overlap": c.overlap, "source_coverage": c.source_coverage,
                "supporting_evidence_ids": [str(l.dossier_evidence_id) for l in c.links if l.relation == "supports"],
                "contradictory_evidence_ids": [str(l.dossier_evidence_id) for l in c.links if l.relation == "contradicts"],
            }
        )
    return items, total
