"""Embedding persistence for newly collected documents."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.collector import NON_TEXT_SOURCES
from app.intelligence.embeddings import embed_texts, model_name
from app.models import Document, DocumentEmbedding, Source


def embed_pending(db: Session, batch_size: int = 256) -> int:
    """Embed all text documents that have no embedding yet. Returns number embedded."""
    total = 0
    while True:
        docs = db.scalars(
            select(Document)
            .join(Source, Source.id == Document.source_id)
            .outerjoin(DocumentEmbedding, DocumentEmbedding.document_id == Document.id)
            .where(DocumentEmbedding.document_id.is_(None), Source.key.notin_(NON_TEXT_SOURCES))
            .limit(batch_size)
        ).all()
        if not docs:
            return total
        vecs = embed_texts([d.normalized_text for d in docs])
        for d, v in zip(docs, vecs):
            db.add(DocumentEmbedding(document_id=d.id, embedding=v.tolist(), model=model_name()))
        db.commit()
        total += len(docs)
