"""Discovery API on real PostgreSQL: validation, pagination, filtering, sorting, detail/history/overview/runs."""
import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.models import Topic, TrendObservation, TrendRun

T0 = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


@pytest.fixture()
def client(db):
    from app.core.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _run(db, key, status="completed", at=T0, **kw):
    r = TrendRun(run_key=key, status=status, started_at=at, completed_at=at if status == "completed" else None, window_end=at,
                 documents_processed=50, model_version="bertopic+m", formula_version="v1.0", configuration={"window_days": 7}, **kw)
    db.add(r)
    db.commit()
    return r


def _topic(db, name, run, score, life, volumes, direction="steady", sources=None, created=T0 - timedelta(days=60), terms=None, growth=20.0, review=False, withheld_cov=0.8):
    t = Topic(name=name, terms=terms or name.lower().split(), embedding=[0.1] * 384, model_version="m", run_id="r", last_run_id=run.id,
              last_observed_at=run.completed_at, created_at=created, needs_review=review, review_reasons=["generic topic name"] if review else [])
    db.add(t)
    db.flush()
    sources = sources or {"google_news": 6, "reddit": 3}
    db.add(TrendObservation(
        topic_id=t.id, run_id=run.id, window_start=T0 - timedelta(days=7), window_end=T0, document_volume=volumes[-1], growth=60.0, momentum=50.0,
        novelty=30.0, trend_score=score, lifecycle=life,
        coverage={"signal_weight_coverage": withheld_cov, "min_coverage": 0.5, "sources_observed": len(sources), "available_signals": ["growth"], "missing_signals": ["engagement"], "identity": {"outcome": "matched"}},
        raw_signals={"volumes": volumes, "growth_pct": growth, "momentum_direction": direction, "momentum_pp": 10.0 if direction == "accelerating" else -5.0,
                     "topic_size": sum(sources.values()), "source_counts": sources},
        formula_version="v1.0", model_version="m"))
    db.commit()
    return t


@pytest.fixture()
def seeded(db):
    r = _run(db, "k1")
    return {
        "run": r,
        "agents": _topic(db, "Coding Agents", r, 82.0, "growing", [1, 2, 4, 8, 12, 18], "accelerating", growth=50.0),
        "rust": _topic(db, "Rust Compiler", r, 55.0, "emerging", [0, 0, 0, 1, 2, 6], "accelerating", {"google_news": 4}, created=T0 - timedelta(days=2), growth=200.0),
        "solar": _topic(db, "Solar Storage", r, None, "declining", [9, 8, 7, 5, 4, 3], "decelerating", {"google_news": 5}, growth=-25.0, withheld_cov=0.3),
        "tax": _topic(db, "Tax Policy", r, 30.0, "peaking", [5, 6, 7, 7, 7, 6], "steady", {"google_news": 2, "reddit": 2, "youtube": 1}, review=True),
    }


def names(resp):
    return [x["topic_name"] for x in resp.json()]


def test_list_defaults_and_pagination_headers(client, seeded):
    r = client.get("/api/trends")
    assert r.status_code == 200 and names(r) == ["Coding Agents", "Rust Compiler", "Tax Policy", "Solar Storage"]  # score desc, withheld last
    assert r.headers["x-total-count"] == "4" and r.headers["x-limit"] == "50" and r.headers["x-offset"] == "0"
    p = client.get("/api/trends?limit=2&offset=1")
    assert names(p) == ["Rust Compiler", "Tax Policy"] and p.headers["x-total-count"] == "4"
    assert client.get("/api/trends?limit=2&offset=10").json() == []


@pytest.mark.parametrize("qs", ["limit=0", "limit=500", "offset=-1", "lifecycle=booming", "sort=nonsense", "order=sideways", "min_score=101",
                                "min_sources=0", "activity_state=dead", "momentum=fast", "max_age_days=0"])
def test_invalid_parameters_are_rejected_with_422(client, seeded, qs):
    assert client.get(f"/api/trends?{qs}").status_code == 422


def test_filters(client, seeded):
    assert names(client.get("/api/trends?lifecycle=emerging")) == ["Rust Compiler"]
    assert names(client.get("/api/trends?momentum=accelerating")) == ["Coding Agents", "Rust Compiler"]
    assert names(client.get("/api/trends?min_sources=2")) == ["Coding Agents", "Tax Policy"]
    assert names(client.get("/api/trends?min_sources=3")) == ["Tax Policy"]
    assert names(client.get("/api/trends?min_score=60")) == ["Coding Agents"]  # withheld scores never pass a score filter
    assert names(client.get("/api/trends?score_withheld=true")) == ["Solar Storage"]
    assert names(client.get("/api/trends?is_new=true")) == ["Rust Compiler"]
    assert names(client.get("/api/trends?q=compiler")) == ["Rust Compiler"]
    assert names(client.get("/api/trends?q=AGENTS")) == ["Coding Agents"]
    assert client.get("/api/trends?q=zzz").json() == [] and client.get("/api/trends?q=zzz").headers["x-total-count"] == "0"
    assert names(client.get("/api/trends?lifecycle=growing&min_score=50")) == ["Coding Agents"]


def test_sorting(client, seeded):
    assert names(client.get("/api/trends?sort=score&order=asc")) == ["Tax Policy", "Rust Compiler", "Coding Agents", "Solar Storage"]  # None last either way
    assert names(client.get("/api/trends?sort=growth")) == ["Rust Compiler", "Coding Agents", "Tax Policy", "Solar Storage"]
    assert names(client.get("/api/trends?sort=name&order=asc")) == ["Coding Agents", "Rust Compiler", "Solar Storage", "Tax Policy"]
    assert names(client.get("/api/trends?sort=documents"))[0] == "Coding Agents"


def test_activity_state_filter_and_freshness_filter(db, client, seeded):
    old = _run(db, "k0", at=T0 - timedelta(days=30))
    _topic(db, "Old Topic", old, 40.0, "declining", [3, 2, 1, 0, 0, 0], growth=-100.0)
    # latest completed run is the newer one: the old topic was absent from it
    assert "Old Topic" not in names(client.get("/api/trends"))
    assert names(client.get("/api/trends?activity_state=stale")) + names(client.get("/api/trends?activity_state=inactive")) == ["Old Topic"]
    assert "Old Topic" in names(client.get("/api/trends?activity_state=all"))
    assert "Old Topic" not in names(client.get("/api/trends?activity_state=all&max_age_days=7"))


def test_detail_contract(client, seeded):
    d = client.get(f"/api/trends/{seeded['agents'].id}").json()
    assert d["topic_name"] == "Coding Agents" and d["trend_score"] == 82.0 and d["score_withheld"] is False and d["activity_state"] == "active"
    assert d["lifecycle"] == "growing" and d["weekly_volumes"] == [1, 2, 4, 8, 12, 18] and d["momentum_direction"] == "accelerating"
    assert d["source_distribution"] == {"google_news": 6, "reddit": 3} and d["growth_pct"] == 50.0
    assert d["explanation"]["acceleration"]["label"] == "sustained_acceleration"
    assert {m["signal"] for m in d["explanation"]["missing"]} >= {"engagement"}
    assert d["last_run"]["status"] == "completed" and d["identity"] == {"outcome": "matched"}
    assert {x["topic_id"] for x in d["related_topic_details"]} <= {str(t.id) for k, t in seeded.items() if k != "run" and t.id != seeded["agents"].id}
    w = client.get(f"/api/trends/{seeded['solar'].id}").json()
    assert w["trend_score"] is None and w["score_withheld"] is True
    assert client.get(f"/api/trends/{seeded['tax'].id}").json()["needs_review"] is True


def test_not_found_and_bad_ids(client, seeded):
    ghost = "00000000-0000-0000-0000-000000000000"
    for path in (f"/api/trends/{ghost}", "/api/trends/not-a-uuid", f"/api/trends/{ghost}/history", "/api/trends/not-a-uuid/history", f"/api/trends/runs/{ghost}", "/api/trends/runs/zzz"):
        assert client.get(path).status_code == 404, path


def test_history_is_ordered_timezone_aware_and_flags_legacy(db, client, seeded):
    t = seeded["agents"]
    later = _run(db, "k2", at=T0 + timedelta(days=7))
    db.add(TrendObservation(topic_id=t.id, run_id=later.id, window_start=T0, window_end=T0 + timedelta(days=7), document_volume=25, trend_score=90.0, lifecycle="growing",
                            coverage={}, raw_signals={"volumes": [2, 4, 8, 12, 18, 25], "growth_pct": 38.9, "momentum_pp": 12.0, "momentum_direction": "accelerating"}, formula_version="v1.0", model_version="m"))
    db.add(TrendObservation(topic_id=t.id, run_id=None, window_start=T0 - timedelta(days=14), window_end=T0 - timedelta(days=7), document_volume=8, trend_score=40.0, lifecycle="growing", coverage={}, raw_signals={}, formula_version="v0", model_version="m"))
    db.commit()
    h = client.get(f"/api/trends/{t.id}/history").json()
    assert [p["document_volume"] for p in h] == [8, 18, 25]  # ascending window_end
    assert h[0]["legacy"] is True and h[0]["run_id"] is None and h[1]["legacy"] is False and h[1]["run_id"] == str(seeded["run"].id)
    assert h[2]["momentum"] == 12.0 and h[2]["momentum_direction"] == "accelerating" and h[2]["growth"] == 38.9
    print([p["window_end"] for p in h])
    assert all(re.search(r"(Z|[+-]\d\d:\d\d)$", p["window_end"]) for p in h)  # timezone-aware ISO strings
    assert len(client.get(f"/api/trends/{t.id}/history?limit=2").json()) == 2
    assert client.get(f"/api/trends/{t.id}/history?limit=0").status_code == 422


def test_overview_counts_and_state(db, client, seeded):
    o = client.get("/api/trends/overview").json()
    assert o["total_active_trends"] == 4 and o["emerging_trends"] == 1 and o["rising_trends"] == 1 and o["declining_trends"] == 1 and o["peaking_trends"] == 1
    assert o["accelerating_trends"] == 2 and o["withheld_score_trends"] == 1 and o["new_trends"] == 1 and o["needs_review_trends"] == 1
    assert o["stale_trends"] == 0 and o["latest_run_status"] == "completed" and o["documents_analyzed"] == 50
    assert o["latest_successful_run"]["run_id"] == str(seeded["run"].id) and o["data_freshness"]["overdue"] is True  # fixture run is old
    _run(db, "kf", status="failed", at=T0 + timedelta(days=1), error_message="boom")
    o2 = client.get("/api/trends/overview").json()
    assert o2["latest_run_status"] == "failed" and o2["total_active_trends"] == 4 and o2["latest_successful_run"]["run_id"] == str(seeded["run"].id)


def test_overview_with_no_runs_is_well_formed(client, db):
    o = client.get("/api/trends/overview").json()
    assert o["total_active_trends"] == 0 and o["latest_successful_run"] is None and o["latest_run"] is None and o["data_freshness"]["overdue"] is True


def test_runs_endpoints_filter_paginate_and_never_leak_secrets(db, client, seeded):
    _run(db, "kf", status="failed", at=T0 + timedelta(days=1), error_message="connect failed postgresql://u:topsecret@host/db password=hunter2")
    r = client.get("/api/trends/runs")
    assert r.status_code == 200 and [x["status"] for x in r.json()] == ["failed", "completed"] and r.headers["x-total-count"] == "2"
    assert [x["status"] for x in client.get("/api/trends/runs?status=failed").json()] == ["failed"]
    assert len(client.get("/api/trends/runs?limit=1&offset=1").json()) == 1
    assert client.get("/api/trends/runs?status=weird").status_code == 422
    blob = r.text
    assert "topsecret" not in blob and "hunter2" not in blob
    detail = client.get(f"/api/trends/runs/{seeded['run'].id}").json()
    assert detail["configuration"] == {"window_days": 7} and "rejection" in detail
