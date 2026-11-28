"""Phase 2 dossier tests on a real PostgreSQL + pgvector database (fake embeddings and LLM).

These prove wiring, persistence, concurrency guards, failure recovery and the claim/section rules. They do NOT
measure the quality of real embeddings or a real LLM.
"""
import hashlib
import os
import subprocess
import sys
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models import ClaimEvidence, Document, DocumentEmbedding, DossierClaim, DossierEvidence, ResearchDossier, Source
from app.research.synthesizer import SynthesisResult
from app.services import dossier_service as svc

from .conftest import BACKEND, URL, fake_embed
from .helpers import NOW


def add(db, source, ext, title, desc, host="a.com", days_old=2, article=None, status=None):
    src = db.scalar(select(Source).where(Source.key == source))
    norm = f"{title}. {desc}" + (f"\n\n{article}" if article else "")
    d = Document(
        source_id=src.id, external_id=ext, title=title, description=desc, normalized_text=norm,
        url=f"https://{host}/{ext}", canonical_url=f"https://{host}/{ext}", content_hash=ext,
        published_at=NOW - timedelta(days=days_old), engagement={}, metadata_={},
        article_status=status or ("full" if article else "rss_only"), article_text=article,
    )
    db.add(d)
    db.flush()
    db.add(DocumentEmbedding(document_id=d.id, embedding=fake_embed([norm])[0].tolist(), model="fake", text_hash=hashlib.sha256(norm.encode()).hexdigest()))
    db.commit()
    return d


@pytest.fixture()
def env(db, engine, monkeypatch):
    from app.core.database import get_db
    from app.main import app

    s = get_settings()
    monkeypatch.setattr(s, "dossier_inline_execution", True)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(svc, "SessionLocal", factory)
    monkeypatch.setattr(svc, "embed_pending", lambda db: 0)
    app.dependency_overrides[get_db] = lambda: db
    llm = {"answer": "Coding agents are gaining adoption among developers [1].", "findings": ["Developers use coding agents in terminals [2]"]}

    def fake(q, ctx, n):
        return SynthesisResult(answer=llm["answer"], key_findings=llm["findings"], model="fake-llm")

    monkeypatch.setattr("app.research.synthesizer.synthesize", fake)
    yield TestClient(app), db, llm, factory
    app.dependency_overrides.clear()


def seed(db):
    add(db, "google_news", "n1", "Coding agents gain adoption among developers", "developers adopt coding agents quickly", host="a.com", days_old=1)
    add(db, "reddit", "r1", "Developers use coding agents in terminals", "developers discuss coding agents in terminals daily", host="b.com", days_old=3)
    add(db, "google_news", "n2", "Enterprise teams pilot coding agents", "enterprise teams pilot coding agents for developers", host="c.com", days_old=6)


def make(client, **kw):
    body = {"query": "coding agents developers", "sources": ["google_news", "reddit"], **kw}
    return client.post("/api/research/dossiers", json=body)


def test_end_to_end_dossier_has_all_sections_claims_and_separate_quality(env):
    client, db, llm, _ = env
    seed(db)
    r = make(client)
    assert r.status_code == 202, r.text
    d = client.get(f"/api/research/dossiers/{r.json()['id']}").json()
    assert d["processing"]["status"] == "completed" and d["processing"]["has_content"]
    assert set(d["sections"]) == {"overview", "key_developments", "supporting_evidence", "contradictory_evidence", "key_entities", "evidence_gaps", "research_questions"}
    assert d["sections"]["contradictory_evidence"]["text"] == "No contradictory evidence was identified in the available dataset."
    assert d["sections"]["overview"]["text"] and d["evidence_count"] == 3 and d["claim_count"] == 2
    dims = d["evidence_quality"]["dimensions"]
    assert set(dims) == {"coverage", "source_diversity", "temporal", "claim_support"}
    assert all(v["text"].endswith("evidence coverage") for v in dims.values())
    assert "confidence" not in str(d["evidence_quality"]).lower().replace("not a probability", "")
    assert d["versions"]["dossier_engine"] and d["versions"]["model"] == "fake-llm"
    claims = client.get(f"/api/research/dossiers/{d['id']}/claims").json()
    assert {c["status"] for c in claims} <= {"supported", "partially_supported"}
    assert all(c["supporting_evidence_ids"] for c in claims)


def test_duplicate_creation_returns_existing_dossier(env):
    client, db, *_ = env
    seed(db)
    a, b = make(client), make(client)
    assert a.json()["id"] == b.json()["id"] and b.json()["created"] is False and b.status_code == 200
    assert db.scalar(select(func.count()).select_from(ResearchDossier)) == 1


def test_only_one_generation_can_claim_a_dossier(env):
    client, db, *_ = env
    seed(db)
    d, _ = svc.create_dossier(db, query="coding agents developers", sources=["google_news"])
    assert svc.claim_run(db, d.id) is True
    assert svc.claim_run(db, d.id) is False  # already running
    db.execute(text("UPDATE research_dossiers SET started_at = now() - interval '2 hours'"))
    db.commit()
    assert svc.claim_run(db, d.id) is True  # crashed run is reclaimable


def test_failed_refresh_keeps_previous_result_and_records_sanitized_error(env, monkeypatch):
    client, db, *_ = env
    seed(db)
    did = make(client).json()["id"]
    before = client.get(f"/api/research/dossiers/{did}").json()
    monkeypatch.setattr(svc, "_compute", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom password=hunter2")))
    r = client.post(f"/api/research/dossiers/{did}/refresh")
    assert r.status_code == 202
    after = client.get(f"/api/research/dossiers/{did}").json()
    assert after["processing"]["status"] == "failed" and "hunter2" not in after["processing"]["error"]
    assert after["sections"] == before["sections"] and after["evidence_count"] == before["evidence_count"]
    assert after["generation"] == before["generation"] and after["generated_at"] == before["generated_at"]


def test_failed_first_generation_recovers_on_retry(env, monkeypatch):
    client, db, *_ = env
    seed(db)
    real = svc._compute
    monkeypatch.setattr(svc, "_compute", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("first attempt")))
    did = make(client).json()["id"]
    assert client.get(f"/api/research/dossiers/{did}").json()["processing"]["status"] == "failed"
    monkeypatch.setattr(svc, "_compute", real)
    again = make(client)
    assert again.json()["id"] == did
    assert client.get(f"/api/research/dossiers/{did}").json()["processing"]["status"] == "completed"


def test_refresh_replaces_content_atomically_and_increments_generation(env):
    client, db, *_ = env
    seed(db)
    did = make(client).json()["id"]
    client.post(f"/api/research/dossiers/{did}/refresh")
    d = client.get(f"/api/research/dossiers/{did}").json()
    assert d["generation"] == 2 and d["evidence_count"] == 3
    assert db.scalar(select(func.count()).select_from(DossierEvidence)) == 3


def test_insufficient_evidence_dossier_is_honest(env):
    client, db, *_ = env
    d = client.get(f"/api/research/dossiers/{make(client, query='quantum toaster firmware').json()['id']}").json()
    assert d["processing"]["status"] == "completed"
    assert d["sections"]["overview"]["text"].startswith("Insufficient evidence")
    assert d["evidence_quality"]["dimensions"]["coverage"]["label"] == "insufficient"
    assert any(g["code"] == "no_evidence" for g in d["sections"]["evidence_gaps"]["items"])


def test_llm_failure_still_produces_a_dossier(env, monkeypatch):
    client, db, *_ = env
    seed(db)
    monkeypatch.setattr("app.research.synthesizer.synthesize", lambda *a: (_ for _ in ()).throw(TimeoutError("llm down")))
    d = client.get(f"/api/research/dossiers/{make(client).json()['id']}").json()
    assert d["processing"]["status"] == "completed" and d["sections"]["overview"]["degraded"] is True
    assert any(g["code"] == "llm_unavailable" for g in d["sections"]["evidence_gaps"]["items"])
    assert d["claim_count"] == 0 and d["sections"]["overview"]["text"].startswith("The language model was unavailable")


def test_article_text_is_used_for_excerpt_and_citation_verification(env):
    client, db, llm, _ = env
    sentence = "Procurement teams at regional banks validated autonomous refactoring pipelines during the pilot."
    add(db, "google_news", "art1", "Banks test coding agents", "short feed blurb", host="a.com",
        article=f"Intro paragraph about the sector. {sentence} Closing remarks follow here for length.", status="full")
    llm["answer"] = "Regional banks validated autonomous refactoring pipelines in a pilot [1]."
    llm["findings"] = []
    d = client.get(f"/api/research/dossiers/{make(client, query='banks coding agents refactoring').json()['id']}").json()
    ev = client.get(f"/api/research/dossiers/{d['id']}/evidence").json()
    assert ev[0]["excerpt_basis"] == "article" and "refactoring pipelines" in ev[0]["excerpt"] and ev[0]["article_status"] == "full"
    claims = client.get(f"/api/research/dossiers/{d['id']}/claims").json()
    assert claims[0]["status"] == "supported"  # supported by article text that the RSS blurb alone does not contain


def test_rss_only_document_is_never_reported_as_article(env):
    client, db, llm, _ = env
    seed(db)
    did = make(client).json()["id"]
    ev = client.get(f"/api/research/dossiers/{did}/evidence").json()
    assert {e["excerpt_basis"] for e in ev} == {"rss"} and {e["article_status"] for e in ev} == {"rss_only"}
    gaps = client.get(f"/api/research/dossiers/{did}").json()["sections"]["evidence_gaps"]["items"]
    assert any(g["code"] == "feed_summaries_only" for g in gaps)


def test_contradictory_evidence_is_detected_and_listed(env):
    client, db, llm, _ = env
    seed(db)
    add(db, "reddit", "c1", "Developers do not use coding agents in terminals", "developers discuss why coding agents fail in terminals", host="d.com", days_old=2)
    llm["answer"] = "Developers use coding agents in terminals [2]."
    llm["findings"] = []
    d = client.get(f"/api/research/dossiers/{make(client).json()['id']}").json()
    contra = d["sections"]["contradictory_evidence"]
    assert contra["items"] and contra["text"] is None
    claims = client.get(f"/api/research/dossiers/{d['id']}/claims?status=contradicted").json()
    assert claims and claims[0]["contradictory_evidence_ids"]
    roles = {e["role"] for e in client.get(f"/api/research/dossiers/{d['id']}/evidence").json()}
    assert "contradictory" in roles


def test_unverified_and_invalid_citations_are_flagged_not_hidden(env):
    client, db, llm, _ = env
    seed(db)
    llm["answer"] = "Quantum toasters will dominate kitchens [1]. Agents are popular [9]. Developers use coding agents in terminals [2]."
    llm["findings"] = ["An uncited statement about coding agents"]
    d = client.get(f"/api/research/dossiers/{make(client).json()['id']}").json()
    by = {c["text"][:20]: c["status"] for c in client.get(f"/api/research/dossiers/{d['id']}/claims").json()}
    assert by["Quantum toasters wil"] == "unverified" and by["Agents are popular."] == "unverified"
    assert any(g["code"] == "unverified_claims" for g in d["sections"]["evidence_gaps"]["items"])
    assert "Quantum" not in d["sections"]["overview"]["text"]


def test_evidence_filters_pagination_and_errors(env):
    client, db, *_ = env
    seed(db)
    did = make(client).json()["id"]
    r = client.get(f"/api/research/dossiers/{did}/evidence?limit=2")
    assert len(r.json()) == 2 and r.headers["X-Total-Count"] == "3"
    assert len(client.get(f"/api/research/dossiers/{did}/evidence?publisher=b.com").json()) == 1
    assert client.get(f"/api/research/dossiers/{did}/evidence?role=bogus").status_code == 422
    assert client.get("/api/research/dossiers/not-a-uuid").status_code == 404
    assert client.get("/api/research/dossiers/00000000-0000-0000-0000-000000000000/claims").status_code == 404
    assert client.post("/api/research/dossiers", json={}).status_code == 422
    assert client.post("/api/research/dossiers", json={"topic_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404
    assert client.post(f"/api/research/dossiers/00000000-0000-0000-0000-000000000000/refresh").status_code == 404
    assert client.get("/api/research/dossiers").headers["X-Total-Count"] == "1"


def test_topic_dossier_uses_topic_id_and_member_documents(env):
    client, db, *_ = env
    from app.models import Topic, TopicDocument

    seed(db)
    docs = db.scalars(select(Document)).all()
    t = Topic(name="Coding agents", terms=["agents", "developers"], model_version="m", run_id="r")
    db.add(t)
    db.flush()
    db.add(TopicDocument(topic_id=t.id, document_id=docs[0].id, probability=0.9))
    db.commit()
    r = client.post("/api/research/dossiers", json={"topic_id": str(t.id)})
    assert r.status_code == 202 and r.json()["topic_id"] == str(t.id) and r.json()["title"] == "Coding agents"
    d = client.get(f"/api/research/dossiers/{r.json()['id']}").json()
    assert d["diagnostics"]["processed_query"]["topic_ids"] == [str(t.id)] and d["evidence_count"] >= 1
    assert client.post("/api/research/dossiers", json={"topic_id": str(t.id)}).json()["id"] == d["id"]


def test_diagnostics_report_methods_reasons_and_no_confidence_claim(env):
    client, db, *_ = env
    seed(db)
    add(db, "google_news", "dup", "Coding agents gain adoption among developers", "developers adopt coding agents quickly", host="a.com", days_old=1)
    d = client.get(f"/api/research/dossiers/{make(client).json()['id']}").json()
    diag = d["diagnostics"]
    assert diag["candidates_retrieved"] >= 4 and diag["selected"] == 3 and diag["rejection_reasons"]
    assert "not a measure of factual accuracy" in diag["note"] and diag["date_coverage"]["distinct_days"] >= 2
    assert all("match_method" in i for i in diag["items"])


def test_stale_embedding_detection_and_refresh_marks_text_change(env):
    from app.ingestion.article_refresh import refresh_articles, stale_embedding_count
    from app.ingestion.article_fetcher import FetchOutcome
    from app.ingestion.article_extractor import ExtractionResult

    _, db, *_ = env
    d = add(db, "google_news", "s1", "Article title", "feed text", host="a.com")
    assert stale_embedding_count(db) == 0
    body = "Real article sentence number one is here. " * 12
    out = refresh_articles(db, [d.id], 5, fetch=lambda url: FetchOutcome(ExtractionResult(body.strip(), "extracted", "trafilatura"), None))
    assert out["extracted"] == 1 and out["changed_text"] == 1
    db.expire_all()
    fresh = db.get(Document, d.id)
    assert fresh.article_status in ("full", "partial") and fresh.article_text_hash and "Real article sentence" in fresh.normalized_text
    assert stale_embedding_count(db) == 1  # fingerprint changed -> embedding is stale until embed_pending runs
    failed = add(db, "google_news", "s2", "Other", "x", host="a.com")
    refresh_articles(db, [failed.id], 5, fetch=lambda url: FetchOutcome(None, "http_403"))
    db.expire_all()
    assert db.get(Document, failed.id).article_status == "failed" and db.get(Document, failed.id).article_failure_reason == "http_403"


def test_database_constraints_for_dossier_tables(env):
    from sqlalchemy.exc import IntegrityError

    _, db, *_ = env
    seed(db)
    d, _ = svc.create_dossier(db, query="coding agents developers")
    doc = db.scalar(select(Document))
    db.add(DossierEvidence(dossier_id=d.id, document_id=doc.id, rank=1, role="bogus"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(DossierEvidence(dossier_id=d.id, document_id=doc.id, rank=1, role="context"))
    db.commit()
    db.add(DossierEvidence(dossier_id=d.id, document_id=doc.id, rank=2, role="context"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.delete(db.get(ResearchDossier, d.id))  # cascades
    db.commit()
    assert db.scalar(select(func.count()).select_from(DossierEvidence)) == 0


def test_migration_004_up_down_and_idempotent_with_create_all(engine):
    from app.core.database import Base

    env_ = {**os.environ, "DATABASE_URL": URL}
    alembic = lambda *a: subprocess.run([sys.executable, "-m", "alembic", *a], cwd=BACKEND, env=env_, capture_output=True, text=True)
    assert alembic("downgrade", "003").returncode == 0
    with engine.connect() as c:
        assert not c.execute(text("SELECT to_regclass('public.research_dossiers')")).scalar()
        cols = {r[0] for r in c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='documents'"))}
        assert "article_status" not in cols
    Base.metadata.tables["research_dossiers"].create(engine, checkfirst=True)  # what create_all would already have done
    r = alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    with engine.connect() as c:
        cols = {r[0] for r in c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='documents'"))}
        assert {"article_status", "article_text", "article_text_hash", "article_failure_reason"} <= cols
        for t in ("dossier_evidence", "dossier_claims", "claim_evidence"):
            assert c.execute(text(f"SELECT to_regclass('public.{t}')")).scalar()
    assert alembic("upgrade", "head").returncode == 0


def test_synthetic_retrieval_regression_metrics(env):
    """Controlled regression on three synthetic topical clusters (labels are by construction). This guards the
    pipeline wiring; it is NOT an estimate of real-world retrieval quality."""
    from app.evaluation.research_quality import diversity, duplicate_rate
    from app.evaluation.retrieval import aggregate, evaluate_query
    from app.research.context_builder import select_evidence
    from app.research.query_processor import process_query
    from app.research.ranker import rank
    from app.research.retriever import retrieve

    from .helpers import seed_three_clusters

    _, db, *_ = env
    seed_three_clusters(db, 10)
    rows = []
    for cluster, q in [("kubernetes", "kubernetes operators scaling"), ("rust", "rust compiler borrow"), ("solar", "solar battery storage")]:
        pq = process_query(q, "30d")
        cands = retrieve(db, pq.cleaned, ["google_news"], "30d", keywords=pq.keywords, phrases=pq.phrases)
        chosen = select_evidence(rank(cands, pq.keywords, 30, phrases=pq.phrases), max_items=5)
        relevant = {u for (u,) in db.execute(select(Document.url).where(Document.external_id.like(f"{cluster}-%")))}
        m = evaluate_query([r.candidate.document.url for r in chosen], relevant, 5)
        m["dup"] = duplicate_rate([r.candidate.document.canonical_url or r.candidate.document.url for r in chosen])
        rows.append(m)
    print("SYNTHETIC_REGRESSION", aggregate(rows))
    assert all(r["precision@5"] == 1.0 and r["mrr"] == 1.0 for r in rows)
