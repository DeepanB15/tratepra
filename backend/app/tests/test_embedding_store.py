
from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid

import numpy as np
import pytest
from sqlalchemy.dialects import postgresql

from app.ingestion import embedding_store


def make_document(text="Original document text"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        normalized_text=text,
    )


def make_embedding(text_hash, model="test-model"):
    return SimpleNamespace(
        embedding=[0.1, 0.2, 0.3],
        model=model,
        text_hash=text_hash,
    )


def setup_mocks(monkeypatch, rows, model="test-model"):
    db = MagicMock()
    select_calls = 0

    def execute_mock(statement):
        nonlocal select_calls

        compiled = statement.compile(
            dialect=postgresql.dialect()
        )
        sql = str(compiled).upper()

        result = MagicMock()

        if "INSERT INTO DOCUMENT_EMBEDDINGS" in sql:
            result.rowcount = 1
            return result

        result.all.return_value = (
            rows if select_calls == 0 else []
        )
        select_calls += 1

        return result

    db.execute.side_effect = execute_mock

    monkeypatch.setattr(
        embedding_store,
        "model_name",
        lambda: model,
    )

    monkeypatch.setattr(
        embedding_store,
        "embed_texts",
        lambda texts: np.array(
            [[0.4, 0.5, 0.6] for _ in texts]
        ),
    )

    return db


def get_upsert_statements(db):
    statements = []

    for call in db.execute.call_args_list:
        statement = call.args[0]

        if not hasattr(statement, "compile"):
            continue

        compiled = statement.compile(
            dialect=postgresql.dialect()
        )
        sql = str(compiled).upper()

        if "INSERT INTO DOCUMENT_EMBEDDINGS" in sql:
            statements.append((statement, compiled, sql))

    return statements


def test_text_hash_is_deterministic():
    assert (
        embedding_store._text_hash("hello")
        == embedding_store._text_hash("hello")
    )

    assert (
        embedding_store._text_hash("hello")
        != embedding_store._text_hash("world")
    )


def test_new_document_gets_embedding(monkeypatch):
    document = make_document()
    db = setup_mocks(monkeypatch, [(document, None)])

    count = embedding_store.embed_pending(db)

    assert count == 1
    assert len(get_upsert_statements(db)) == 1
    db.commit.assert_called_once()


def test_unchanged_document_is_skipped(monkeypatch):
    document = make_document()

    fingerprint = embedding_store._text_hash(
        document.normalized_text
    )

    existing = make_embedding(fingerprint)

    db = setup_mocks(
        monkeypatch,
        [(document, existing)],
    )

    count = embedding_store.embed_pending(db)

    assert count == 0
    assert get_upsert_statements(db) == []
    db.commit.assert_not_called()


def test_changed_text_refreshes_existing_embedding(monkeypatch):
    document = make_document("Updated document text")

    old_hash = embedding_store._text_hash(
        "Original document text"
    )

    existing = make_embedding(old_hash)

    db = setup_mocks(
        monkeypatch,
        [(document, existing)],
    )

    count = embedding_store.embed_pending(db)

    assert count == 1
    assert len(get_upsert_statements(db)) == 1
    db.commit.assert_called_once()


def test_changed_model_refreshes_existing_embedding(monkeypatch):
    document = make_document()

    fingerprint = embedding_store._text_hash(
        document.normalized_text
    )

    existing = make_embedding(
        fingerprint,
        model="old-model",
    )

    db = setup_mocks(
        monkeypatch,
        [(document, existing)],
        model="new-model",
    )

    count = embedding_store.embed_pending(db)

    assert count == 1
    assert len(get_upsert_statements(db)) == 1
    db.commit.assert_called_once()


def test_invalid_batch_size():
    with pytest.raises(ValueError):
        embedding_store.embed_pending(
            MagicMock(),
            batch_size=0,
        )


def test_insert_and_update_are_conditioned_on_original_text(
    monkeypatch,
):
    document = make_document("Original document text")
    original_text = document.normalized_text

    db = setup_mocks(
        monkeypatch,
        [(document, None)],
    )

    def change_text_during_embedding(texts):
        document.normalized_text = "Changed while embedding"

        return np.array([[0.4, 0.5, 0.6]])

    monkeypatch.setattr(
        embedding_store,
        "embed_texts",
        change_text_during_embedding,
    )

    embedding_store.embed_pending(db)

    statements = get_upsert_statements(db)

    assert len(statements) == 1

    _, compiled, sql = statements[0]

    assert "DOCUMENTS.NORMALIZED_TEXT" in sql
    assert original_text in compiled.params.values()
    assert (
        "Changed while embedding"
        not in compiled.params.values()
    )
