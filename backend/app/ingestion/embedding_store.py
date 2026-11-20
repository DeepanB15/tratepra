
"""Embedding persistence with text and model version tracking."""

import hashlib

from sqlalchemy import literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ingestion.collector import NON_TEXT_SOURCES
from app.intelligence.embeddings import embed_texts, model_name
from app.models import Document, DocumentEmbedding, Source


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def embed_pending(db: Session, batch_size: int = 256) -> int:
    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero")

    total = 0
    current_model = model_name()
    last_id = None

    while True:
        query = (
            select(Document, DocumentEmbedding)
            .join(Source, Source.id == Document.source_id)
            .outerjoin(
                DocumentEmbedding,
                DocumentEmbedding.document_id == Document.id,
            )
            .where(Source.key.notin_(NON_TEXT_SOURCES))
            .order_by(Document.id)
            .limit(batch_size)
        )

        if last_id is not None:
            query = query.where(Document.id > last_id)

        rows = db.execute(query).all()

        if not rows:
            break

        last_id = rows[-1][0].id
        stale_documents = []

        for document, existing in rows:
            text = document.normalized_text or ""
            fingerprint = _text_hash(text)

            if (
                existing is None
                or existing.text_hash != fingerprint
                or existing.model != current_model
            ):
                stale_documents.append(
                    (document.id, text, fingerprint)
                )

        if not stale_documents:
            continue

        vectors = embed_texts(
            [text for _, text, _ in stale_documents]
        )

        if len(vectors) != len(stale_documents):
            raise ValueError(
                "Embedding count does not match document count"
            )

        for (document_id, text, fingerprint), vector in zip(
            stale_documents, vectors
        ):
            current_text_matches = (
                select(Document.id)
                .where(
                    Document.id == document_id,
                    Document.normalized_text == text,
                )
                .exists()
            )

            statement = insert(DocumentEmbedding).from_select(
                [
                    "document_id",
                    "embedding",
                    "model",
                    "text_hash",
                ],
                select(
                    literal(
                        document_id,
                        type_=DocumentEmbedding.document_id.type,
                    ),
                    literal(
                        vector.tolist(),
                        type_=DocumentEmbedding.embedding.type,
                    ),
                    literal(
                        current_model,
                        type_=DocumentEmbedding.model.type,
                    ),
                    literal(
                        fingerprint,
                        type_=DocumentEmbedding.text_hash.type,
                    ),
                )
                .select_from(Document)
                .where(
                    Document.id == document_id,
                    Document.normalized_text == text,
                ),
            )

            statement = statement.on_conflict_do_update(
                index_elements=[DocumentEmbedding.document_id],
                set_={
                    "embedding": statement.excluded.embedding,
                    "model": statement.excluded.model,
                    "text_hash": statement.excluded.text_hash,
                },
                where=current_text_matches,
            )

            result = db.execute(statement)
            total += result.rowcount or 0

        db.commit()

    return total
