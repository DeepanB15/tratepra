"""Dependency health checks. Each check is isolated: one failing dependency never marks another as failed."""
import time
from typing import Any

import httpx
from sqlalchemy import text

from app.connectors import all_connectors
from app.core.config import get_settings
from app.core.database import engine


def _timed(fn) -> dict[str, Any]:
    started = time.time()
    try:
        out = fn() or {}
        return {"ok": True, "latency_ms": int((time.time() - started) * 1000), **out}
    except Exception as exc:
        return {"ok": False, "latency_ms": int((time.time() - started) * 1000), "error": f"{type(exc).__name__}: {exc}"[:300]}


def check_database() -> dict[str, Any]:
    def run():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    return _timed(run)


def check_pgvector() -> dict[str, Any]:
    """Extension present, a real vector operation works, and the stored dimension matches config."""

    def run():
        with engine.connect() as conn:
            ext = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")).scalar()
            if ext is None:
                raise RuntimeError("pgvector extension is not enabled (CREATE EXTENSION vector;)")
            conn.execute(text("SELECT '[1,2,3]'::vector <=> '[1,2,4]'::vector")).scalar()
            dim = conn.execute(
                text(
                    "SELECT a.atttypmod FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
                    "WHERE c.relname = 'document_embeddings' AND a.attname = 'embedding' AND NOT a.attisdropped"
                )
            ).scalar()
        configured = get_settings().embedding_dim
        info: dict[str, Any] = {"version": ext, "configured_dimension": configured, "table_dimension": dim}
        if dim is not None and dim != configured:
            raise RuntimeError(f"embedding dimension mismatch: table={dim}, EMBEDDING_DIM={configured}")
        return info

    return _timed(run)


def check_ollama() -> dict[str, Any]:
    s = get_settings()

    def run():
        resp = httpx.get(f"{s.ollama_base_url}/api/tags", timeout=3.0)
        resp.raise_for_status()
        names = [m.get("name", "") for m in resp.json().get("models", [])]
        wanted = s.ollama_model
        available = any(n == wanted or n.split(":")[0] == wanted.split(":")[0] and wanted in n for n in names)
        if not available:
            raise RuntimeError(f"Ollama is running but model '{wanted}' is not pulled (ollama pull {wanted})")
        return {"model": wanted}

    return _timed(run)


def check_connectors(db_states: dict[str, dict] | None = None) -> list[dict[str, Any]]:
    out = []
    for c in all_connectors():
        a = c.availability()
        if db_states and c.key in db_states:
            a.update(db_states[c.key])
        out.append(a)
    return out


def readiness() -> dict[str, Any]:
    """Overall: ready (DB + pgvector ok), degraded (also needs Ollama), not_ready (DB or pgvector failed)."""
    db = check_database()
    vec = check_pgvector() if db["ok"] else {"ok": False, "error": "skipped: database unavailable"}
    ollama = check_ollama()
    components = {"database": db, "pgvector": vec, "ollama": ollama}
    core_ok = db["ok"] and vec["ok"]
    status = "not_ready" if not core_ok else ("ready" if ollama["ok"] else "degraded")
    return {"status": status, "components": components, "connectors": check_connectors()}
