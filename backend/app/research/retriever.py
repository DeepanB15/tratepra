"""Hybrid retrieval over stored documents.

Two candidate generators are merged:
  semantic - pgvector cosine distance on document embeddings
  keyword  - PostgreSQL full-text search (OR over query terms, contiguous match for phrases)
Keyword retrieval finds exact names and technical terms that an embedding can miss; semantic
retrieval finds paraphrases that share no words. Final ordering is done by research/ranker.py
(semantic + keyword + freshness + source quality), so every candidate carries a semantic score.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, func, literal_column, or_, select
from sqlalchemy.orm import Session

from app.connectors.base import parse_time_range
from app.ingestion.collector import NON_TEXT_SOURCES
from app.intelligence.embeddings import embed_query
from app.models import Document, DocumentEmbedding, Source


@dataclass
class Candidate:
    document: Document
    source_key: str
    semantic: float  # 0-100 (cosine similarity x100)
    quality: float  # 0-100
    match: str = "semantic"  # semantic | keyword | both
    keyword_rank: float | None = None


def build_tsquery(keywords: list[str], phrases: list[str]) -> str | None:
    """Safe to_tsquery text: alphanumeric terms OR-ed together; phrases as adjacent-word matches."""
    parts: list[str] = []
    for k in keywords:
        t = re.sub(r"[^A-Za-z0-9]", "", k)
        if len(t) > 1:
            parts.append(t)
    for ph in phrases:
        words = [re.sub(r"[^A-Za-z0-9]", "", w) for w in ph.split()]
        words = [w for w in words if w]
        if len(words) >= 2:
            parts.append("(" + " <-> ".join(words) + ")")
    return " | ".join(dict.fromkeys(parts)) or None


def _filters(keys: list[str], cutoff: datetime):
    return [
        Source.key.in_(keys),
        # Publication time; documents with unknown publication time fall back to collection time.
        or_(
            Document.published_at >= cutoff,
            and_(Document.published_at.is_(None), Document.collected_at >= cutoff),
        ),
    ]


def retrieve(
    db: Session,
    query: str,
    sources: list[str],
    time_range: str,
    limit: int = 60,
    keywords: list[str] | None = None,
    phrases: list[str] | None = None,
) -> list[Candidate]:
    keys = [s for s in sources if s not in NON_TEXT_SOURCES]
    if not keys:
        return []
    cutoff = datetime.now(timezone.utc) - parse_time_range(time_range)
    qvec = embed_query(query).tolist()
    distance = DocumentEmbedding.embedding.cosine_distance(qvec)

    def base(*extra_cols):
        return (
            select(Document, Source.key, Source.quality_weight, distance.label("dist"), *extra_cols)
            .join(DocumentEmbedding, DocumentEmbedding.document_id == Document.id)
            .join(Source, Source.id == Document.source_id)
            .where(*_filters(keys, cutoff))
        )

    merged: dict = {}

    for doc, key, quality, dist, *_ in db.execute(base().order_by(distance).limit(limit)).all():
        merged[doc.id] = Candidate(doc, key, _sim(dist), float(quality), "semantic")

    tsq_text = build_tsquery(keywords or [], phrases or [])
    if tsq_text:
        # Expression must match the GIN index ix_documents_fts.
        tsvector = func.to_tsvector(literal_column("'english'"), literal_column("documents.normalized_text"))
        tsq = func.to_tsquery(literal_column("'english'"), tsq_text)
        rank_col = func.ts_rank_cd(tsvector, tsq).label("kw_rank")
        stmt = base(rank_col).where(tsvector.op("@@")(tsq)).order_by(rank_col.desc()).limit(limit)
        for doc, key, quality, dist, kw_rank in db.execute(stmt).all():
            existing = merged.get(doc.id)
            if existing:
                existing.match, existing.keyword_rank = "both", float(kw_rank)
            else:
                merged[doc.id] = Candidate(doc, key, _sim(dist), float(quality), "keyword", float(kw_rank))
    return list(merged.values())


def _sim(dist: float) -> float:
    return max(0.0, min(1.0, 1.0 - float(dist))) * 100.0
