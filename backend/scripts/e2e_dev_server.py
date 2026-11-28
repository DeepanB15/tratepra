"""DEV/TEST ONLY: run the API on an isolated, throw-away local database with fake embeddings and no LLM.

Used for browser end-to-end checks. Refuses any database that is not on localhost and named *_e2e.
Never point this at a real (e.g. Supabase) database: it drops and recreates the schema.
"""
import os
import subprocess
import sys

DB = os.environ.get("E2E_DATABASE_URL", "postgresql+psycopg2://postgres@localhost:5544/tratepra_e2e")
if "localhost" not in DB and "127.0.0.1" not in DB or not DB.rsplit("/", 1)[-1].endswith("_e2e"):
    sys.exit("Refusing: E2E database must be local and named *_e2e")
os.environ["DATABASE_URL"] = DB
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"  # unreachable -> extractive fallback path
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ["APP_ENV"] = "development"

from sqlalchemy import create_engine, text  # noqa: E402

admin = create_engine(DB.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT")
with admin.connect() as c:
    name = DB.rsplit("/", 1)[-1]
    c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    c.execute(text(f'CREATE DATABASE "{name}"'))
eng = create_engine(DB)
with eng.begin() as c:
    c.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=os.environ)

import numpy as np  # noqa: E402


def fake_embed(texts):
    out = []
    for t in texts:
        v = np.zeros(384, dtype=np.float32)
        for w in t.lower().split():
            v[hash(w) % 384] += 1.0
        n = np.linalg.norm(v)
        out.append(v / n if n else v)
    return np.array(out)


for mod in ("app.intelligence.embeddings", "app.research.retriever", "app.ingestion.embedding_store", "app.services.research_service"):
    m = __import__(mod, fromlist=["x"])
    if hasattr(m, "embed_texts"):
        m.embed_texts = fake_embed
    if hasattr(m, "embed_query"):
        m.embed_query = lambda t: fake_embed([t])[0]

from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.services.source_service import ensure_sources  # noqa: E402

ensure_sources()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.tests.integration.helpers import NOW, keyword_fit, seed_three_clusters  # noqa: E402
from app.services.trend_run_service import recompute  # noqa: E402

with SessionLocal() as db:
    seed_three_clusters(db, 10)
    from sqlalchemy import update  # give seeded docs a feed description, like real RSS items
    from app.models import Document

    db.execute(update(Document).values(description=Document.normalized_text))
    db.commit()
    recompute(db, NOW, False, keyword_fit())
print("seeded; starting server on :8010", flush=True)
get_settings()
import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=8010, log_level="warning")
