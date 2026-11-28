"""Safe, bounded re-extraction of article text for existing documents, plus stale-embedding detection.

Fetching reuses the SSRF-safe fetcher (public-address check on every redirect, size and time limits).
Network I/O happens with NO database transaction open; only the final write locks the row. When the composed
normalized text changes, the stored embedding's text_hash no longer matches - that mismatch IS the stale mark,
and embed_pending re-embeds exactly those rows.
"""
import logging

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.ingestion.article_fetcher import fetch_article_outcome
from app.ingestion.article_state import build_state, compose_normalized_text
from app.models import Document, DocumentEmbedding

log = logging.getLogger(__name__)
RETRYABLE = ("rss_only", "failed", "unavailable")


def stale_embedding_count(db: Session) -> int:
    """Embeddings whose text_hash no longer matches sha256(normalized_text)."""
    return int(
        db.scalar(
            select(func.count())
            .select_from(DocumentEmbedding)
            .join(Document, Document.id == DocumentEmbedding.document_id)
            .where(DocumentEmbedding.text_hash != text("encode(sha256(convert_to(documents.normalized_text,'UTF8')),'hex')"))
        )
        or 0
    )


def base_text(title: str, description: str | None) -> str:
    return f"{title}. {description}" if description else title


def refresh_articles(db: Session, document_ids: list, max_docs: int = 5, fetch=fetch_article_outcome) -> dict:
    """Try to (re)extract article text for up to `max_docs` retryable documents. Returns a summary dict."""
    rows = db.execute(
        select(Document.id, Document.url, Document.title, Document.description)
        .where(Document.id.in_(document_ids), Document.article_status.in_(RETRYABLE), Document.url.is_not(None))
        .limit(max_docs)
    ).all()
    db.rollback()  # release the read transaction before any network I/O
    summary = {"attempted": 0, "extracted": 0, "failed": 0, "changed_text": 0}
    for doc_id, url, title, description in rows:
        summary["attempted"] += 1
        try:
            outcome = fetch(url)
        except Exception:  # never let one article break a dossier
            log.exception("article refresh failed")
            summary["failed"] += 1
            continue
        state = build_state(outcome.result.text if outcome.result else None, outcome.reason)
        doc = db.scalar(select(Document).where(Document.id == doc_id).with_for_update())
        if doc is None:
            continue
        for k, v in state.items():
            setattr(doc, k, v)
        if state["article_text"]:
            new_text = compose_normalized_text(base_text(title, description), state["article_text"])
            if new_text != doc.normalized_text:
                doc.normalized_text = new_text  # embedding text_hash now mismatches => stale until embed_pending runs
                summary["changed_text"] += 1
            summary["extracted"] += 1
        else:
            summary["failed"] += 1
        db.commit()
    return summary
