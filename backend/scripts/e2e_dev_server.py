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

# Monitoring seed: give the newest observation of each topic a *comparable* earlier completed snapshot (lower growth/score)
# so that follow -> detection -> events -> notifications can be exercised in the browser. Synthetic, dev only.
from datetime import timedelta  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.models import TrendObservation, TrendRun  # noqa: E402

with SessionLocal() as db:
    for cur in db.scalars(select(TrendObservation).where(TrendObservation.run_id.is_not(None))).all():
        run = db.get(TrendRun, cur.run_id)
        prev_run = TrendRun(run_key=f"e2e-prev-{cur.id}", status="completed", started_at=run.started_at - timedelta(days=7),
                            completed_at=run.completed_at - timedelta(days=7), window_end=run.window_end - timedelta(days=7), formula_version=run.formula_version)
        db.add(prev_run)
        db.flush()
        # the seeded corpus is too small for a scored observation (score withheld); give the *current* one explicit synthetic values
        srcs = {"google_news": 4, "reddit": 3, "hacker_news": 3}
        cur.trend_score, cur.growth, cur.lifecycle = 60.0, 40.0, "growing"
        cur.raw_signals = {**(cur.raw_signals or {}), "growth_pct": 40.0, "momentum_pp": 45.0, "momentum_direction": "accelerating", "source_counts": srcs}
        cur.coverage = {**(cur.coverage or {}), "signal_weight_coverage": 0.9}
        db.add(TrendObservation(topic_id=cur.topic_id, run_id=prev_run.id, window_start=cur.window_start - timedelta(days=7), window_end=cur.window_end - timedelta(days=7),
                                document_volume=max(1, (cur.document_volume or 2) // 2), growth=-5.0, trend_score=(cur.trend_score or 40) - 20, lifecycle="emerging",
                                formula_version=cur.formula_version, model_version=cur.model_version, created_at=cur.created_at - timedelta(days=7),
                                raw_signals={**(cur.raw_signals or {}), "growth_pct": -5.0, "source_counts": srcs}, coverage=cur.coverage))
    db.commit()
print("seeded; starting server on :8010", flush=True)
get_settings()
import uvicorn  # noqa: E402

from app.main import app  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=8010, log_level="warning")
