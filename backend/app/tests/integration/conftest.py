"""Integration tests run against a REAL PostgreSQL + pgvector database.

Set TEST_DATABASE_URL (e.g. postgresql+psycopg2://postgres@localhost:5544/tratepra_it). The schema in that
database is DROPPED and rebuilt with `alembic upgrade head` - never point this at a database you care about.
Skipped when the variable is unset. Embedding model, LLM and connectors are replaced by deterministic fakes,
so these tests prove database/pipeline behaviour, NOT the quality of real embeddings or real services.
"""
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

URL = os.environ.get("TEST_DATABASE_URL")
BACKEND = Path(__file__).resolve().parents[3]


def pytest_collection_modifyitems(config, items):
    if URL:
        return
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL not set (needs PostgreSQL + pgvector)")
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)


def fake_embed(texts):
    """Deterministic bag-of-words hash embedding (384-d, unit norm)."""
    out = []
    for t in texts:
        v = np.zeros(384, dtype=np.float32)
        for w in re.findall(r"[a-z0-9]+", t.lower()):
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 384] += 1.0
        n = np.linalg.norm(v)
        out.append(v / n if n else v)
    return np.array(out)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(URL)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
    env = {**os.environ, "DATABASE_URL": URL}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine, monkeypatch):
    for mod in ("app.intelligence.embeddings", "app.research.retriever", "app.ingestion.embedding_store", "app.services.research_service"):
        m = __import__(mod, fromlist=["x"])
        if hasattr(m, "embed_texts"):
            monkeypatch.setattr(m, "embed_texts", fake_embed)
        if hasattr(m, "embed_query"):
            monkeypatch.setattr(m, "embed_query", lambda t: fake_embed([t])[0])
    with engine.begin() as c:
        c.execute(text("TRUNCATE research_evidence, research_results, research_queries, documents, sources, collection_logs, topics CASCADE"))
    s = sessionmaker(bind=engine)()
    from app.models import Source

    for key in ("google_news", "youtube", "reddit", "google_trends"):
        s.add(Source(key=key, name=key, quality_weight=70.0))
    s.commit()
    yield s
    s.close()
