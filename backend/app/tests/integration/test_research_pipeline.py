"""Pipeline test: real DB + fake embeddings/LLM/connectors. Proves wiring and persistence, not real-service quality."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import ResearchEvidence, ResearchResult
from app.research.synthesizer import SynthesisResult
from app.services import research_service

from .conftest import fake_embed
from .test_database import add_doc


def _fake_llm(answer, findings):
    return lambda q, ctx, n: SynthesisResult(answer=answer, key_findings=findings, model="fake-llm")


def test_run_research_persists_verified_answer_and_transparency(db, monkeypatch):
    add_doc(db, "google_news", "n1", "Terminal coding agents gain adoption", "developers adopt coding agents quickly")
    add_doc(db, "reddit", "r1", "Coding agents thread", "developers discuss coding agents in terminals")
    monkeypatch.setattr(
        research_service, "synthesize",
        _fake_llm("Developers are adopting coding agents [1]. Quantum toasters will win [2]. Uncited claim about agents.", ["Coding agents discussed [2]"]),
    )
    out = research_service.run_research(db, "coding agents developers", ["google_news", "reddit"], "30d", refresh=False)
    assert out["model"] == "fake-llm"
    assert out["evidence"] and all(e["url"] for e in out["evidence"])
    reasons = " ".join(u["reason"] for u in out["unverified_claims"])
    assert "no citation" in reasons
    assert "Quantum" not in out["answer"]
    t = out["transparency"]
    assert t["evidence_selected"] == len(out["evidence"]) and t["sources_searched"] == 2
    assert set(t["timing_ms"]) == {"collection", "embedding", "retrieval", "synthesis", "total"}
    assert db.scalar(select(ResearchResult)).retrieval_metadata["unverified_claims"]
    assert db.scalars(select(ResearchEvidence)).all()


def test_no_evidence_is_reported_honestly(db):
    out = research_service.run_research(db, "something nobody collected", ["google_news"], "30d", refresh=False)
    assert out["evidence"] == [] and "No relevant evidence" in out["answer"]


def test_api_search_validation_and_health(db, engine, monkeypatch):
    from app.core.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    try:
        c = TestClient(app)
        assert c.post("/api/research/search", json={"query": "the of a", "refresh": False}).status_code == 422
        assert c.post("/api/research/search", json={"query": "ab"}).status_code == 422
        r = c.post("/api/research/search", json={"query": "coding agents", "refresh": False, "sources": ["google_news"]})
        assert r.status_code == 200 and "transparency" in r.json()
        assert c.get("/api/research/does-not-exist").status_code == 404
        assert c.get("/health").json()["status"] == "ok"
        assert c.get("/ready").status_code in (200, 503)
    finally:
        app.dependency_overrides.clear()
