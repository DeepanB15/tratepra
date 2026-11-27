import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import Document, DocumentEmbedding, Source
from app.research.retriever import retrieve

from .conftest import fake_embed

NOW = datetime.now(timezone.utc)


def add_doc(db, source_key, ext, title, desc="", days_old=1):
    src = db.scalar(select(Source).where(Source.key == source_key))
    d = Document(
        source_id=src.id, external_id=ext, title=title, description=desc,
        normalized_text=f"{title}. {desc}", url=f"https://example.com/{ext}", canonical_url=f"https://example.com/{ext}",
        content_hash=ext, published_at=NOW - timedelta(days=days_old), engagement={}, metadata_={},
    )
    db.add(d)
    db.flush()
    db.add(DocumentEmbedding(document_id=d.id, embedding=fake_embed([d.normalized_text])[0].tolist(), model="fake", text_hash=hashlib.sha256(d.normalized_text.encode()).hexdigest()))
    db.commit()
    return d


def test_schema_has_pgvector_indexes_and_dimension(engine):
    with engine.connect() as c:
        idx = {r[0] for r in c.execute(text("select indexname from pg_indexes where schemaname='public'"))}
    assert {"ix_documents_fts", "ix_document_embeddings_hnsw"} <= idx
    with engine.connect() as c:
        dim = c.execute(text(
            "select a.atttypmod from pg_attribute a join pg_class t on t.oid=a.attrelid "
            "where t.relname='document_embeddings' and a.attname='embedding'")).scalar()
    assert dim == 384


def test_unique_source_external_id(db):
    add_doc(db, "google_news", "a1", "Title one")
    with pytest.raises(IntegrityError):
        add_doc(db, "google_news", "a1", "Title one again")
    db.rollback()


def test_hybrid_retrieval_finds_keyword_only_and_semantic(db):
    add_doc(db, "google_news", "k1", "Rust borrow checker released", "new compiler features")
    add_doc(db, "reddit", "k2", "Cooking pasta at home", "recipe tips")
    got = retrieve(db, "rust borrow checker", ["google_news", "reddit"], "30d", keywords=["rust", "borrow", "checker"], phrases=["borrow checker"])
    top = max(got, key=lambda c: c.semantic)
    assert top.document.external_id == "k1"
    assert any(c.match in ("keyword", "both") for c in got)


def test_retrieval_respects_window_and_sources(db):
    add_doc(db, "google_news", "old", "Rust news from long ago", days_old=90)
    add_doc(db, "youtube", "yt", "Rust video", days_old=1)
    got = retrieve(db, "rust", ["google_news"], "30d", keywords=["rust"])
    assert got == []  # old one outside window, youtube not requested
