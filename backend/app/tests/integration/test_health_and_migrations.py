import os
import subprocess
import sys

from sqlalchemy import inspect, text

from app.core import health

from .conftest import BACKEND, URL


def test_ready_reports_database_and_pgvector_on_real_postgres(engine, monkeypatch):
    monkeypatch.setattr(health, "engine", engine)
    r = health.readiness()
    assert r["components"]["database"]["ok"] and r["components"]["pgvector"]["ok"]
    assert r["status"] in ("ready", "degraded")  # degraded when Ollama is not running


def test_migration_downgrade_and_reupgrade(engine):
    env = {**os.environ, "DATABASE_URL": URL}
    run = lambda *a: subprocess.run([sys.executable, "-m", "alembic", *a], cwd=BACKEND, env=env, capture_output=True, text=True)
    r = run("downgrade", "base")
    assert r.returncode == 0, r.stderr
    assert "documents" not in inspect(engine).get_table_names()
    r = run("upgrade", "head")
    assert r.returncode == 0, r.stderr
    assert "documents" in inspect(engine).get_table_names()
    with engine.connect() as c:
        assert c.execute(text("select 1 from pg_extension where extname='vector'")).scalar() == 1
