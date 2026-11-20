"""Research orchestration and persistence."""
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.connectors import CONNECTOR_CLASSES
from app.ingestion.collector import NON_TEXT_SOURCES, collect
from app.ingestion.embedding_store import embed_pending
from app.connectors.base import parse_time_range
from app.models import (
    ResearchEvidence,
    ResearchQuery,
    ResearchResult,
    Topic,
)
from app.research.citation_validator import EvidenceRef, verify_answer
from app.research.context_builder import build_context, select_evidence
from app.research.query_processor import process_query
from app.research.ranker import rank
from app.research.retriever import retrieve
from app.research.synthesizer import synthesize
from app.core.config import get_settings
from app.intelligence.embeddings import embed_query
from app.intelligence.topic_representations import nearest_topics


def _related_topics(db: Session, query: str, k: int = 5) -> list[str]:
    topics = db.scalars(select(Topic).where(Topic.embedding.is_not(None))).all()
    if not topics:
        return []
    q = embed_query(query)
    import numpy as np

    others = {str(t.id): np.asarray(t.embedding, dtype=np.float32) for t in topics}
    names = {str(t.id): t.name for t in topics}
    near = nearest_topics(q, others, k=k)
    return [names[tid] for tid, sim in near if sim >= 0.3]


def _json_safe(status: dict) -> dict:
    """source_status is stored in a JSON column: convert datetimes to ISO strings."""
    out = {}
    for k, v in status.items():
        out[k] = {kk: (vv.isoformat() if isinstance(vv, datetime) else vv) for kk, vv in v.items()}
    return out


def _transparency(source_status: dict, candidates: int, selected: int, timing: dict, claim_stats: dict) -> dict:
    def total(field: str) -> int:
        return sum(int(v.get(field) or 0) for v in source_status.values())

    return {
        "sources_searched": len(source_status),
        "sources_failed": {k: v.get("error") for k, v in source_status.items() if v.get("status") not in ("ok", "skipped")},
        "results_collected": total("fetched"),
        "out_of_window": total("out_of_window"),
        "rejected": total("rejected"),
        "duplicates_removed": total("duplicates"),
        "accepted": total("inserted"),
        "candidates_retrieved": candidates,
        "evidence_selected": selected,
        "claims": claim_stats,
        "timing_ms": timing,
    }


def run_research(db: Session, query: str, sources: list[str], time_range: str, refresh: bool = True) -> dict:
    """Raises InvalidQuery for an unsearchable query."""
    t0 = time.time()
    pq = process_query(query, default_time_range=time_range)  # may raise InvalidQuery
    # An explicit time phrase in the question overrides the request default.
    effective_range = pq.time_range or time_range
    valid_sources = [s for s in dict.fromkeys(sources) if s in CONNECTOR_CLASSES] or list(CONNECTOR_CLASSES)

    if refresh:
        source_status = collect(db, pq.cleaned, valid_sources, effective_range)
    else:
        source_status = {k: {"source": k, "status": "skipped", "error": None} for k in valid_sources}
    t_collect = time.time()
    embed_pending(db)
    t_embed = time.time()

    window_days = max(parse_time_range(effective_range).total_seconds() / 86400.0, 1.0)
    candidates = retrieve(db, pq.cleaned, valid_sources, effective_range, keywords=pq.keywords, phrases=pq.phrases)
    ranked = rank(candidates, pq.keywords, window_days, phrases=pq.phrases)
    selected = select_evidence(ranked)
    ctx = build_context(selected)
    t_retrieve = time.time()

    synth = synthesize(pq.cleaned, ctx.text, len(selected))
    t_synth = time.time()
    refs = [
        EvidenceRef(text=f"{i.candidate.document.title}. {i.candidate.document.description or ''}", url=i.candidate.document.url)
        for i in selected
    ]
    verified = verify_answer(synth.answer, synth.key_findings, refs)

    distribution: dict[str, int] = {}
    for item in selected:
        distribution[item.candidate.source_key] = distribution.get(item.candidate.source_key, 0) + 1

    timing = {
        "collection": int((t_collect - t0) * 1000),
        "embedding": int((t_embed - t_collect) * 1000),
        "retrieval": int((t_retrieve - t_embed) * 1000),
        "synthesis": int((t_synth - t_retrieve) * 1000),
        "total": int((time.time() - t0) * 1000),
    }
    settings = get_settings()
    try:
        q_row = ResearchQuery(query=query, sources=valid_sources, time_range=effective_range)
        db.add(q_row)
        db.flush()
        related = _related_topics(db, pq.cleaned)
        res = ResearchResult(
            query_id=q_row.id,
            answer=verified.answer,
            key_findings=verified.key_findings,
            related_topics=related,
            source_status=_json_safe(source_status),
            source_distribution=distribution,
            model=synth.model,
            execution_ms=timing["total"],
            retrieval_metadata={
                "keywords": pq.keywords,
                "phrases": pq.phrases,
                "intent": pq.intent,
                "time_range": effective_range,
                "candidates": len(candidates),
                "removed_citations": sorted(verified.removed_refs),
                "degraded_synthesis": synth.degraded,
                "unverified_claims": verified.unverified,
                "transparency": _transparency(source_status, len(candidates), len(selected), timing, verified.stats),
                "weights": {
                    "semantic": settings.rank_w_semantic,
                    "keyword": settings.rank_w_keyword,
                    "freshness": settings.rank_w_freshness,
                    "quality": settings.rank_w_quality,
                },
            },
        )
        db.add(res)
        db.flush()
        for i, item in enumerate(selected, start=1):
            db.add(
                ResearchEvidence(
                    result_id=res.id,
                    document_id=item.candidate.document.id,
                    rank=i,
                    relevance=round(item.score, 2),
                    cited=1 if i in verified.cited else 0,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return serialize_result(db, res.id)


def serialize_result(db: Session, result_id) -> dict:
    if not isinstance(result_id, uuid.UUID):
        try:
            result_id = uuid.UUID(str(result_id))
        except ValueError:
            raise LookupError("Research result not found")
    res = db.scalar(
        select(ResearchResult)
        .where(ResearchResult.id == result_id)
        .options(
            joinedload(ResearchResult.query),
            joinedload(ResearchResult.evidence).joinedload(ResearchEvidence.document),
        )
    )
    if res is None:
        raise LookupError("Research result not found")
    meta = res.retrieval_metadata or {}
    evidence = []
    for ev in sorted(res.evidence, key=lambda e: e.rank):
        d = ev.document
        evidence.append(
            {
                "document_id": str(d.id),
                "title": d.title,
                "url": d.url,
                "source": d.source.key,
                "published_at": d.published_at,
                "relevance": ev.relevance,
                "cited": bool(ev.cited),
            }
        )
    return {
        "research_id": str(res.id),
        "query": res.query.query,
        "answer": res.answer,
        "key_findings": res.key_findings,
        "sources_used": res.query.sources,
        "source_status": res.source_status,
        "source_distribution": res.source_distribution,
        "evidence": evidence,
        "related_topics": res.related_topics,
        "model": res.model,
        "degraded": bool(meta.get("degraded_synthesis")),
        "transparency": meta.get("transparency", {}),
        "unverified_claims": meta.get("unverified_claims", []),
        "execution_ms": res.execution_ms,
        "created_at": res.created_at,
    }
