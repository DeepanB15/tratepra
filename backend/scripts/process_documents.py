"""Generate embeddings for all stored documents that lack one.

Usage: python -m scripts.process_documents
"""
from app.core.database import SessionLocal, init_db
from app.core.logging import setup_logging
from app.ingestion.embedding_store import embed_pending


def main() -> None:
    setup_logging()
    init_db()
    with SessionLocal() as db:
        print(f"Embedded {embed_pending(db)} documents")


if __name__ == "__main__":
    main()
