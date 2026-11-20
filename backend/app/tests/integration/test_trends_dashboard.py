"""Read-side trend/dashboard behaviour on real PostgreSQL using hand-inserted observations (no BERTopic run)."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.models import Topic, TrendObservation


def _obs(db, topic, score, life, volumes):
    now = datetime.now(timezone.utc)
    db.add(
        TrendObservation(
            topic_id=topic.id, window_start=now, window_end=now, document_volume=volumes[-1], growth=70.0, momentum=55.0,
            engagement=None, novelty=40.0, search_interest=None, cross_source_activity=100.0, trend_score=score, lifecycle=life,
            coverage={"signal_weight_coverage": 0.75, "min_coverage": 0.5, "sources_observed": 2},
            raw_signals={"volumes": volumes, "growth_pct": 120.0, "topic_size": sum(volumes), "source_counts": {"google_news": 6, "reddit": 3}},
            formula_version="test", model_version="test",
        )
    )
    db.commit()


def test_trend_detail_explanation_and_dashboard(db):
    from app.core.database import get_db
    from app.main import app

    t = Topic(name="Coding Agents", terms=["coding", "agents"], embedding=[0.1] * 384, model_version="test", run_id="r")
    db.add(t)
    db.commit()
    _obs(db, t, 48.0, "growing", [1, 2, 3, 5, 6, 9])
    _obs(db, t, 55.0, "growing", [1, 2, 3, 5, 6, 12])
    app.dependency_overrides[get_db] = lambda: db
    try:
        c = TestClient(app)
        d = c.get(f"/api/trends/{t.id}").json()
        assert d["previous_score"] == 48.0 and d["trend_score"] == 55.0
        assert d["source_distribution"] == {"google_news": 6, "reddit": 3}
        assert {m["signal"] for m in d["explanation"]["missing"]} == {"engagement", "search_interest"}
        assert c.get("/api/trends/not-a-uuid").status_code == 404
        o = c.get("/api/dashboard/overview").json()
        assert o["active_topic_count"] == 1 and o["lifecycle_distribution"]["growing"] == 1
        assert {s["key"] for s in o["sources"]} == {"google_news", "youtube", "reddit", "google_trends"}
        assert all("state" in s for s in o["sources"])
    finally:
        app.dependency_overrides.clear()
