"""Phase 3 monitoring on real PostgreSQL: watchlist, snapshots, detection persistence, dedup/cooldown, notifications,
advisory-lock concurrency, failure policy, scheduler, internal triggers, migration 005."""
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models import (
    Document, DossierClaim, MonitoringJobRun, Notification, ResearchDossier, Topic, TopicDocument, TrendEvent, TrendObservation, TrendRun, TrendWatchlist,
)
from app.monitoring import jobs, pipeline
from app.monitoring.snapshots import load_snapshots

from .conftest import BACKEND, URL
from .helpers import add_docs

BASE = datetime(2026, 10, 1, tzinfo=timezone.utc)
INTERNAL = {"X-Internal-Token": get_settings().internal_api_token}


def mk_topic(db, name="AI coding", emb=None, **kw):
    t = Topic(name=name, terms=["ai", "coding"], model_version="m", run_id="x", embedding=emb, **kw)
    db.add(t)
    db.commit()
    return t


def mk_run(db, i, status="completed", formula="v1.0"):
    end = BASE + timedelta(days=7 * i)
    r = TrendRun(run_key=f"k{uuid.uuid4().hex}", status=status, started_at=end, completed_at=end if status == "completed" else None, window_end=end, formula_version=formula)
    db.add(r)
    db.commit()
    return r


def mk_obs(db, topic, i, vol, growth, lifecycle="growing", status="completed", formula="v1.0", sources=3, score=None, run=None, days=14):
    run = run or mk_run(db, i, status, formula)
    end = BASE + timedelta(days=7 * i)
    o = TrendObservation(
        topic_id=topic.id, run_id=run.id, window_start=end - timedelta(days=days), window_end=end, document_volume=vol, growth=growth,
        trend_score=score if score is not None else 40.0 + 5 * i, lifecycle=lifecycle, formula_version=formula, model_version="m", created_at=end,
        raw_signals={"growth_pct": growth, "momentum_pp": 1.0, "momentum_direction": "steady", "source_counts": {f"s{k}": 1 for k in range(sources)}},
        coverage={"signal_weight_coverage": 0.9, "sources_observed": sources},
    )
    db.add(o)
    topic.last_observed_at, topic.last_run_id = end, run.id
    db.commit()
    return o


@pytest.fixture()
def env(db, engine, monkeypatch):
    from app.core.database import get_db
    from app.main import app

    s = get_settings()
    monkeypatch.setattr(s, "monitoring_inline_execution", True)
    monkeypatch.setattr(s, "monitoring_job_retry_delay_seconds", 0.0)
    factory = sessionmaker(bind=engine)
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app), db, factory, engine
    app.dependency_overrides.clear()


def follow(client, topic):
    r = client.post("/api/monitoring/watchlist", json={"topic_id": str(topic.id)})
    assert r.status_code in (200, 201), r.text
    return r.json()


def accelerating_topic(db, name="AI coding"):
    t = mk_topic(db, name)
    mk_obs(db, t, 0, 18, 10, "emerging")
    mk_obs(db, t, 1, 31, 45, "growing")
    return t


# ---------------------------------------------------------------- watchlist
def test_watchlist_follow_is_idempotent_patchable_and_listed_with_score_change(env):
    client, db, *_ = env
    t = accelerating_topic(db)
    a = client.post("/api/monitoring/watchlist", json={"topic_id": str(t.id), "priority": "high", "user_note": "watch"})
    b = client.post("/api/monitoring/watchlist", json={"topic_id": str(t.id)})
    assert a.status_code == 201 and b.status_code == 200 and db.scalar(select(func.count()).select_from(TrendWatchlist)) == 1
    row = client.get("/api/monitoring/watchlist").json()[0]
    assert row["topic_name"] == "AI coding" and row["latest_score"] == 45.0 and row["previous_score"] == 40.0 and row["score_change"] == 5.0
    assert row["lifecycle"] == "growing" and row["growth"] == 45 and row["activity_state"] == "active" and row["priority"] == "high" and row["user_note"] == "watch"
    p = client.patch(f"/api/monitoring/watchlist/{t.id}", json={"monitoring_enabled": False, "priority": "low", "user_note": "x"}).json()
    assert p["monitoring_enabled"] is False and p["priority"] == "low"
    assert client.get("/api/monitoring/watchlist?enabled=true").json() == []
    assert client.get("/api/monitoring/watchlist?q=coding&lifecycle=growing&priority=low").headers["X-Total-Count"] == "1"
    assert client.get("/api/monitoring/watchlist?lifecycle=peaking").json() == []


def test_watchlist_validation_and_errors(env):
    client, db, *_ = env
    assert client.post("/api/monitoring/watchlist", json={"topic_id": str(uuid.uuid4())}).status_code == 404
    assert client.post("/api/monitoring/watchlist", json={"topic_id": "nope"}).status_code == 404
    t = mk_topic(db)
    assert client.post("/api/monitoring/watchlist", json={"topic_id": str(t.id), "priority": "urgent"}).status_code == 422
    assert client.patch(f"/api/monitoring/watchlist/{t.id}", json={"priority": "low"}).status_code == 404  # not followed
    assert client.delete(f"/api/monitoring/watchlist/{t.id}").status_code == 404
    assert client.get("/api/monitoring/watchlist?sort=bogus").status_code == 422
    assert client.get("/api/monitoring/trends/not-a-uuid").status_code == 404


def test_unfollow_keeps_history_and_events_and_inactive_trend_stays_listed(env):
    client, db, *_ = env
    t = accelerating_topic(db)
    follow(client, t)
    pipeline.run_detection(db, now=BASE + timedelta(days=8))
    n_events = db.scalar(select(func.count()).select_from(TrendEvent))
    assert n_events > 0
    for i in range(2, 7):  # five later completed runs that do not include the topic -> it goes stale then inactive
        mk_run(db, i)
    row = client.get("/api/monitoring/watchlist").json()[0]
    assert row["activity_state"] == "inactive" and row["observations"] == 2  # still followed, history intact
    assert client.delete(f"/api/monitoring/watchlist/{t.id}").json() == {"deleted": True}
    assert db.scalar(select(func.count()).select_from(TrendEvent)) >= n_events
    assert db.scalar(select(func.count()).select_from(TrendObservation)) == 2
    assert client.get("/api/monitoring/watchlist").json() == []


# ---------------------------------------------------------------- snapshots
def test_failed_runs_and_legacy_observations_never_become_snapshots(env):
    _, db, *_ = env
    t = mk_topic(db)
    mk_obs(db, t, 0, 20, 10)
    mk_obs(db, t, 1, 40, 80, status="failed")  # observation attached to a failed run
    legacy = mk_obs(db, t, 2, 40, 80)
    legacy.run_id = None  # pre-Phase-1 row: cannot be proven to come from a successful run
    db.commit()
    snaps = load_snapshots(db, t.id)
    assert [s.document_volume for s in snaps] == [20]


def test_snapshots_are_chronological_and_carry_run_and_formula(env):
    client, db, *_ = env
    t = mk_topic(db)
    for i, v in [(2, 30), (0, 10), (1, 20)]:
        mk_obs(db, t, i, v, 5)
    s = load_snapshots(db, t.id)
    assert [x.document_volume for x in s] == [10, 20, 30] and all(x.run_id and x.formula_version == "v1.0" for x in s)
    h = client.get(f"/api/monitoring/trends/{t.id}/history").json()
    assert [x["document_volume"] for x in h] == [10, 20, 30] and h[0]["comparable_with_previous"] is None and h[1]["comparable_with_previous"] is True


# ---------------------------------------------------------------- detection persistence
def test_detection_creates_explained_events_and_is_idempotent(env):
    client, db, *_ = env
    t = accelerating_topic(db)
    follow(client, t)
    first = pipeline.run_detection(db, now=BASE + timedelta(days=8))
    kinds = {e.event_type for e in db.scalars(select(TrendEvent))}
    assert {"growth_acceleration", "lifecycle_transition"} <= kinds and first["created"] >= 2
    again = pipeline.run_detection(db, now=BASE + timedelta(days=9))
    assert again["created"] == 0 and again["duplicates"] >= 2
    e = db.scalar(select(TrendEvent).where(TrendEvent.event_type == "growth_acceleration"))
    assert "from 10% to 45%" in e.explanation and e.detection_version == "cd-1" and e.deduplication_key and e.previous_observation_id and e.current_observation_id
    assert e.details["thresholds"]["min_growth_change_pp"] == 15.0 and e.evidence_document_ids == []
    assert "aggregate observations only" in e.explanation


def test_unfollowed_topics_only_produce_new_emerging_events(env):
    _, db, *_ = env
    t = mk_topic(db, "Brand new thing", created_at=BASE + timedelta(days=0))
    mk_obs(db, t, 0, 15, 50, "emerging")
    db.commit()
    res = pipeline.run_detection(db, now=BASE + timedelta(days=1))
    assert res["created"] == 1 and db.scalar(select(TrendEvent.event_type)) == "new_emerging_trend"
    t2 = accelerating_topic(db, "Other")  # not followed: acceleration/lifecycle are not evaluated
    pipeline.run_detection(db, now=BASE + timedelta(days=9))
    assert not db.scalar(select(func.count()).select_from(TrendEvent).where(TrendEvent.topic_id == t2.id, TrendEvent.event_type != "new_emerging_trend"))


def test_cooldown_suppresses_repeats_unless_severity_rises(env):
    client, db, *_ = env
    t = mk_topic(db)
    mk_obs(db, t, 0, 20, 10)
    mk_obs(db, t, 1, 32, 30)  # +20pp: informational acceleration
    follow(client, t)
    pipeline.run_detection(db, now=BASE + timedelta(days=8))
    mk_obs(db, t, 2, 46, 52)  # +22pp: another informational acceleration inside the cooldown
    r = pipeline.run_detection(db, now=BASE + timedelta(days=9))
    assert r["cooled_down"] == 1 and db.scalar(select(func.count()).select_from(TrendEvent).where(TrendEvent.event_type == "growth_acceleration")) == 1
    mk_obs(db, t, 3, 70, 95)  # +43pp: important -> not suppressed
    pipeline.run_detection(db, now=BASE + timedelta(days=10))
    assert db.scalar(select(func.count()).select_from(TrendEvent).where(TrendEvent.event_type == "growth_acceleration")) == 2
    mk_obs(db, t, 4, 95, 120)  # later, outside the cooldown window -> allowed again
    pipeline.run_detection(db, now=BASE + timedelta(days=12))
    assert db.scalar(select(func.count()).select_from(TrendEvent).where(TrendEvent.event_type == "growth_acceleration")) == 3


def test_failed_collection_does_not_create_inactivity_or_decline_events(env):
    client, db, *_ = env
    t = mk_topic(db)
    mk_obs(db, t, 0, 40, 5)
    mk_obs(db, t, 1, 10, 5)
    follow(client, t)
    for i in range(2, 5):
        mk_run(db, i)
    res = pipeline.run_detection(db, now=BASE + timedelta(days=30), collection_failed=True)
    kinds = {e.event_type for e in db.scalars(select(TrendEvent))}
    assert not kinds & {"activity_decline", "activity_disappearance"} and res["collection_failed"]
    pipeline.run_detection(db, now=BASE + timedelta(days=31), collection_failed=False)
    assert {"activity_decline", "activity_disappearance"} <= {e.event_type for e in db.scalars(select(TrendEvent))}


def test_incompatible_formula_versions_are_not_compared_in_persistence(env):
    client, db, *_ = env
    t = mk_topic(db)
    mk_obs(db, t, 0, 20, 10, "emerging", formula="v1.0")
    mk_obs(db, t, 1, 60, 90, "growing", formula="v2.0")
    follow(client, t)
    res = pipeline.run_detection(db, now=BASE + timedelta(days=8))
    assert res["created"] == 0 and any("formula changed" in s["reason"] for s in res["suppressed"])


# ---------------------------------------------------------------- evidence association
def test_new_supporting_evidence_links_documents_and_skips_old_ones(env):
    client, db, *_ = env
    t = mk_topic(db)
    mk_obs(db, t, 0, 20, 10)
    mk_obs(db, t, 1, 22, 12)
    follow(client, t)
    docs = add_docs(db, "kubernetes", 5)
    for i, d in enumerate(docs):
        d.collected_at = BASE - timedelta(days=1) if i < 2 else BASE + timedelta(days=8)  # 2 predate the previous snapshot, 3 are newer
        db.add(TopicDocument(topic_id=t.id, document_id=d.id, probability=0.9))
    db.commit()
    r = pipeline.run_evidence_association(db, now=BASE + timedelta(days=9))
    assert r["created"] == 1
    e = db.scalar(select(TrendEvent).where(TrendEvent.event_type == "new_supporting_evidence"))
    assert e.current_value == 3 and len(e.evidence_document_ids) == 3 and "3 document(s) attached" in e.explanation
    assert pipeline.run_evidence_association(db, now=BASE + timedelta(days=10))["created"] == 0
    ev = client.get(f"/api/monitoring/events/{e.id}").json()
    assert len(ev["evidence"]) == 3 and ev["evidence"][0]["url"]


def test_contradictory_evidence_uses_latest_dossier_claims_only(env):
    client, db, *_ = env
    t = mk_topic(db)
    mk_obs(db, t, 0, 20, 10)
    mk_obs(db, t, 1, 22, 12)
    follow(client, t)
    dossier = ResearchDossier(dossier_key="k1", topic_id=t.id, query_text="q", status="completed", generated_at=BASE + timedelta(days=3), sections={})
    db.add(dossier)
    db.flush()
    db.add(DossierClaim(dossier_id=dossier.id, claim_no=1, text="Developers use coding agents in terminals", status="supported"))
    docs = add_docs(db, "kubernetes", 3)
    docs[0].title, docs[0].description = "Developers do not use coding agents in terminals", ""
    for d in docs:
        d.collected_at = BASE + timedelta(days=8)
        db.add(TopicDocument(topic_id=t.id, document_id=d.id, probability=0.9))
    db.commit()
    r = pipeline.run_evidence_association(db, now=BASE + timedelta(days=9))
    c = db.scalar(select(TrendEvent).where(TrendEvent.event_type == "contradictory_evidence"))
    assert c is not None and c.severity == "important" and c.evidence_document_ids == [str(docs[0].id)] and "wording heuristic" in c.explanation
    assert r["claim_checks"] >= 3
    db.delete(dossier)  # no dossier -> no contradiction events can exist
    db.commit()
    db.execute(text("DELETE FROM trend_events"))
    db.commit()
    assert pipeline.run_evidence_association(db, now=BASE + timedelta(days=10))["created"] == 1  # only the supporting-evidence event
    assert not db.scalar(select(func.count()).select_from(TrendEvent).where(TrendEvent.event_type == "contradictory_evidence"))


def test_new_related_topic_event_keeps_identities_separate(env):
    client, db, *_ = env
    v = [1.0] + [0.0] * 383
    w = mk_topic(db, "Watched", emb=v)
    mk_obs(db, w, 0, 20, 10)
    mk_obs(db, w, 1, 21, 11)
    follow(client, w)
    n_close = mk_topic(db, "Close newcomer", emb=[0.9] + [0.1] + [0.0] * 382)
    n_far = mk_topic(db, "Far newcomer", emb=[0.0, 1.0] + [0.0] * 382)
    run = db.scalar(select(TrendRun).order_by(TrendRun.completed_at.desc()))
    for n in (n_close, n_far):
        mk_obs(db, n, 1, 10, 5, run=run)
    pipeline.run_detection(db, now=BASE + timedelta(days=8))
    e = db.scalars(select(TrendEvent).where(TrendEvent.event_type == "new_related_topic")).all()
    assert len(e) == 1 and e[0].details["related_name"] == "Close newcomer" and "remain separate" in e[0].explanation
    assert db.scalar(select(func.count()).select_from(Topic)) == 3  # nothing merged


# ---------------------------------------------------------------- events + notifications
def test_event_state_and_notification_state_are_independent_and_history_is_preserved(env):
    client, db, *_ = env
    t = accelerating_topic(db)
    follow(client, t)
    pipeline.run_detection(db, now=BASE + timedelta(days=8))
    assert pipeline.prepare_notifications(db)["created"] >= 2
    assert pipeline.prepare_notifications(db)["created"] == 0  # idempotent
    assert client.get("/api/monitoring/notifications/unread-count").json()["unread"] >= 2
    n = client.get("/api/monitoring/notifications").json()[0]
    eid = n["event_id"]
    # reading the notification does not touch the event
    assert client.patch(f"/api/monitoring/notifications/{n['id']}", json={"read": True}).json()["read"] is True
    assert client.get(f"/api/monitoring/events/{eid}").json()["state"] == "new"
    # dismissing the event in the feed does not touch the notification
    assert client.patch(f"/api/monitoring/events/{eid}", json={"state": "dismissed"}).json()["state"] == "dismissed"
    notif = db.get(Notification, uuid.UUID(n["id"]))
    db.refresh(notif)
    assert notif.dismissed_at is None and notif.read_at is not None
    # dismissing the notification keeps the event and the notification row
    client.patch(f"/api/monitoring/notifications/{n['id']}", json={"dismissed": True})
    assert db.get(TrendEvent, uuid.UUID(eid)) is not None
    assert all(x["id"] != n["id"] for x in client.get("/api/monitoring/notifications?status=all").json())
    assert any(x["id"] == n["id"] for x in client.get("/api/monitoring/notifications?status=dismissed").json())
    assert client.patch(f"/api/monitoring/events/{eid}", json={"state": "bogus"}).status_code == 422
    assert client.patch(f"/api/monitoring/events/{uuid.uuid4()}", json={"state": "read"}).status_code == 404


def test_mark_all_read_and_unread_count(env):
    client, db, *_ = env
    follow(client, accelerating_topic(db))
    pipeline.run_detection(db, now=BASE + timedelta(days=8))
    pipeline.prepare_notifications(db)
    before = client.get("/api/monitoring/notifications/unread-count").json()
    assert before["unread"] > 0 and set(before["by_severity"]) <= {"informational", "important", "critical"}
    assert client.post("/api/monitoring/notifications/mark-all-read").json()["marked"] == before["unread"]
    assert client.get("/api/monitoring/notifications/unread-count").json()["unread"] == 0
    assert len(client.get("/api/monitoring/notifications?status=all").json()) == before["unread"]  # history kept


def test_notification_preferences_filter_by_severity_and_type_but_events_remain(env):
    client, db, *_ = env
    t = accelerating_topic(db)
    follow(client, t)
    r = client.put("/api/monitoring/preferences", json={"min_notification_severity": "important", "muted_event_types": ["lifecycle_transition"]})
    assert r.status_code == 200 and client.get("/api/monitoring/preferences").json()["min_notification_severity"] == "important"
    pipeline.run_detection(db, now=BASE + timedelta(days=8))
    res = pipeline.prepare_notifications(db)
    events = db.scalars(select(TrendEvent)).all()
    assert res["created"] == 1 and res["skipped_by_preferences"] == len(events) - 1  # only the important acceleration notifies
    assert len(client.get("/api/monitoring/events").json()) == len(events)  # all remain in the feed
    assert client.put("/api/monitoring/preferences", json={"muted_event_types": ["nonsense"]}).status_code == 422
    assert client.put("/api/monitoring/preferences", json={"min_notification_severity": "loud"}).status_code == 422


def test_event_filters_pagination_and_detail(env):
    client, db, *_ = env
    t = accelerating_topic(db)
    follow(client, t)
    pipeline.run_detection(db, now=BASE + timedelta(days=8))
    r = client.get("/api/monitoring/events?limit=1")
    assert len(r.json()) == 1 and int(r.headers["X-Total-Count"]) >= 2
    assert all(e["event_type"] == "lifecycle_transition" for e in client.get("/api/monitoring/events?event_type=lifecycle_transition").json())
    assert client.get("/api/monitoring/events?severity=critical").json() == []
    assert client.get(f"/api/monitoring/events?topic_id={t.id}").headers["X-Total-Count"] != "0"
    assert client.get(f"/api/monitoring/trends/{t.id}/events").json()
    assert client.get("/api/monitoring/events?event_type=bogus").status_code == 422
    assert client.get("/api/monitoring/events?date_from=2020-01-01T00:00:00Z&date_to=2020-01-02T00:00:00Z").json() == []
    e = client.get("/api/monitoring/events").json()[0]
    d = client.get(f"/api/monitoring/events/{e['id']}").json()
    assert d["explanation"] and d["details"]["comparability"] and d["topic_name"] == "AI coding"


def test_trend_monitoring_detail_marks_viewed_and_links_dossier(env):
    client, db, *_ = env
    t = accelerating_topic(db)
    follow(client, t)
    db.add(ResearchDossier(dossier_key="kk", topic_id=t.id, query_text="q", status="completed", generated_at=BASE))
    db.commit()
    d = client.get(f"/api/monitoring/trends/{t.id}").json()
    assert d["followed"] and d["latest"]["document_volume"] == 31 and d["observation_count"] == 2 and d["dossier"]["has_content"]
    w = db.scalar(select(TrendWatchlist))
    db.refresh(w)
    assert w.last_viewed_at is not None


# ---------------------------------------------------------------- jobs, locks, failures
def test_advisory_lock_prevents_concurrent_execution_of_the_same_job(env):
    _, db, factory, eng = env
    ran = []
    fns = {"detection": lambda d, c: ran.append(1) or {}}
    with jobs.advisory_lock("detection", eng) as held:
        assert held
        r = jobs.run_job("detection", factory=factory, eng=eng, fns=fns)  # second runner while the lock is held
        assert r["status"] == "skipped" and ran == []
        assert jobs.run_job("evidence", factory=factory, eng=eng, fns={"evidence": lambda d, c: {}})["status"] == "completed"  # other jobs unaffected
    assert jobs.run_job("detection", factory=factory, eng=eng, fns=fns)["status"] == "completed" and ran == [1]
    skipped = db.scalar(select(func.count()).select_from(MonitoringJobRun).where(MonitoringJobRun.status == "skipped"))
    assert skipped == 1


def test_two_threads_racing_for_a_job_run_it_once(env):
    _, db, factory, eng = env
    count, gate = [], threading.Event()

    def slow(d, c):
        count.append(1)
        gate.wait(2)
        return {}

    out = []
    th = [threading.Thread(target=lambda: out.append(jobs.run_job("detection", factory=factory, eng=eng, fns={"detection": slow}))) for _ in range(2)]
    th[0].start()
    while not count:
        pass
    th[1].start()
    th[1].join(3)
    gate.set()
    th[0].join(3)
    assert sorted(o["status"] for o in out) == ["completed", "skipped"] and len(count) == 1


def test_job_failure_is_recorded_sanitized_retried_and_bounded(env, monkeypatch):
    _, db, factory, eng = env
    monkeypatch.setattr(get_settings(), "monitoring_job_max_attempts", 3)
    calls = []

    def boom(d, c):
        calls.append(1)
        raise RuntimeError("db down password=hunter2")

    r = jobs.run_job("detection", factory=factory, eng=eng, fns={"detection": boom})
    assert r["status"] == "failed" and len(calls) == 3 and "hunter2" not in r["error"]  # bounded retries, no infinite loop
    row = db.scalar(select(MonitoringJobRun).where(MonitoringJobRun.status == "failed"))
    assert row.attempt == 3 and row.duration_ms is not None and "hunter2" not in row.error_message
    flaky = iter([RuntimeError("once"), None])

    def sometimes(d, c):
        e = next(flaky)
        if e:
            raise e
        return {"ok": 1}

    assert jobs.run_job("evidence", factory=factory, eng=eng, fns={"evidence": sometimes})["status"] == "completed"


def cycle_fns(log, **over):
    def mk(name, ret=None):
        return lambda d, c: (log.append((name, dict(c))), ret or {})[1]

    fns = {n: mk(n) for n in jobs.JOBS}
    fns.update(over)
    return fns


def test_cycle_runs_jobs_in_order_and_records_each(env):
    _, db, factory, eng = env
    log = []
    r = jobs.run_cycle(trigger="manual", factory=factory, eng=eng, fns=cycle_fns(log))
    assert r["status"] == "completed" and [n for n, _ in log] == list(jobs.JOBS)
    assert db.scalar(select(func.count()).select_from(MonitoringJobRun)) == 6  # five jobs + the cycle row
    cyc = db.scalar(select(MonitoringJobRun).where(MonitoringJobRun.job_type == "cycle"))
    assert cyc.status == "completed" and cyc.trigger == "manual" and cyc.duration_ms is not None


def test_collection_failure_still_detects_but_flags_it_and_raises_a_failure_notification(env):
    client, db, factory, eng = env
    log = []

    def bad_collection(d, c):
        c["collection_failed"] = True
        raise RuntimeError("all sources down")

    r = jobs.run_cycle(factory=factory, eng=eng, fns=cycle_fns(log, collection=bad_collection))
    assert r["status"] == "failed" and r["jobs"]["collection"] == "failed" and r["jobs"]["recompute"] == "completed"
    assert dict(log)["detection"]["collection_failed"] is True  # detection is told not to infer inactivity
    ev = db.scalar(select(TrendEvent).where(TrendEvent.event_type == "monitoring_failure"))
    assert ev and ev.severity == "important" and "all sources down" in ev.description and ev.topic_id is None


def test_recompute_failure_skips_detection_and_evidence(env):
    _, db, factory, eng = env
    log = []

    def bad(d, c):
        raise RuntimeError("model exploded")

    r = jobs.run_cycle(factory=factory, eng=eng, fns=cycle_fns(log, recompute=bad))
    assert r["jobs"]["detection"] == "skipped" and r["jobs"]["evidence"] == "skipped" and r["jobs"]["notifications"] == "completed"
    assert "detection" not in [n for n, _ in log] and "evidence" not in [n for n, _ in log]
    assert db.scalar(select(func.count()).select_from(TrendEvent).where(TrendEvent.event_type == "monitoring_failure")) == 1


def test_detection_failure_preserves_existing_events(env):
    client, db, factory, eng = env
    follow(client, accelerating_topic(db))
    pipeline.run_detection(db, now=BASE + timedelta(days=8))
    n = db.scalar(select(func.count()).select_from(TrendEvent))

    def bad(d, c):
        raise RuntimeError("detector crashed")

    r = jobs.run_cycle(factory=factory, eng=eng, fns=cycle_fns([], detection=bad))
    assert r["jobs"]["detection"] == "failed"
    assert db.scalar(select(func.count()).select_from(TrendEvent).where(TrendEvent.event_type != "monitoring_failure")) == n


def test_cycle_does_not_overlap_and_honours_shutdown(env):
    _, db, factory, eng = env
    with jobs.advisory_lock("cycle", eng):
        assert jobs.run_cycle(factory=factory, eng=eng, fns=cycle_fns([]))["status"] == "skipped"
    stop = threading.Event()
    stop.set()
    log = []
    r = jobs.run_cycle(factory=factory, eng=eng, fns=cycle_fns(log), stop=stop)
    assert log == [] and set(r["jobs"].values()) == {"skipped"}


def test_collection_job_skips_without_queries_and_uses_watchlist_names(env, monkeypatch):
    client, db, *_ = env
    assert jobs.collection_queries(db) == []
    assert jobs.job_collection(db, {}) == {"skipped": True, "reason": "no collection queries: nothing is followed and MONITORING_COLLECTION_QUERIES is empty"}
    lo, hi = mk_topic(db, "Low one"), mk_topic(db, "High one")
    follow(client, lo)
    client.patch(f"/api/monitoring/watchlist/{lo.id}", json={"priority": "low"})
    follow(client, hi)
    client.patch(f"/api/monitoring/watchlist/{hi.id}", json={"priority": "high"})
    monkeypatch.setattr(get_settings(), "monitoring_collection_queries", "extra query")
    assert jobs.collection_queries(db) == ["extra query", "High one", "Low one"]
    client.patch(f"/api/monitoring/watchlist/{hi.id}", json={"monitoring_enabled": False})
    assert "High one" not in jobs.collection_queries(db)


def test_collection_job_marks_failure_when_no_source_succeeds(env, monkeypatch):
    client, db, *_ = env
    monkeypatch.setattr(get_settings(), "monitoring_collection_queries", "q1")
    monkeypatch.setattr("app.ingestion.collector.collect", lambda db, q, s, tr: {"google_news": {"status": "error"}, "reddit": {"status": "error"}})
    ctx = {}
    with pytest.raises(RuntimeError):
        jobs.job_collection(db, ctx)
    assert ctx["collection_failed"] is True
    monkeypatch.setattr("app.ingestion.collector.collect", lambda db, q, s, tr: {"google_news": {"status": "ok", "inserted": 2}, "reddit": {"status": "error"}})
    monkeypatch.setattr("app.ingestion.embedding_store.embed_pending", lambda db: 2)
    ctx = {}
    d = jobs.job_collection(db, ctx)
    assert ctx["collection_failed"] is False and d["queries"]["q1"]["sources_failed"] == ["reddit"]  # partial failure is reported, not hidden


# ---------------------------------------------------------------- scheduler / status / internal API
def test_scheduler_due_logic_uses_persisted_last_cycle_and_never_double_runs(env, monkeypatch):
    _, db, factory, eng = env
    monkeypatch.setattr(get_settings(), "monitoring_interval_minutes", 60)
    log = []
    s = jobs.Scheduler(factory=factory, eng=eng, fns=cycle_fns(log))
    s.started_at = datetime.now(timezone.utc)
    assert s.tick() is False and log == []  # not due yet: interval counts from start
    s.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    assert s.tick() is True and len(log) == 5
    assert s.tick() is False and len(log) == 5  # the persisted cycle moves the next due time forward (survives restart)
    s2 = jobs.Scheduler(factory=factory, eng=eng, fns=cycle_fns(log))
    s2.started_at = datetime.now(timezone.utc) - timedelta(hours=5)
    assert s2.tick() is False  # a restarted scheduler still honours the last persisted cycle
    assert jobs.next_due(factory) > datetime.now(timezone.utc)


def test_failed_cycle_waits_for_the_next_interval(env, monkeypatch):
    _, db, factory, eng = env
    monkeypatch.setattr(get_settings(), "monitoring_interval_minutes", 60)
    bad = lambda d, c: (_ for _ in ()).throw(RuntimeError("x"))  # noqa: E731
    s = jobs.Scheduler(factory=factory, eng=eng, fns=cycle_fns([], collection=bad, recompute=bad))
    s.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    assert s.tick() is True
    assert s.tick() is False  # no tight retry loop after a failure


def test_scheduler_thread_starts_stops_and_recovers_interrupted_rows(env, monkeypatch):
    _, db, factory, eng = env
    monkeypatch.setattr(get_settings(), "monitoring_tick_seconds", 1)
    old = MonitoringJobRun(job_type="collection", status="running", started_at=datetime.now(timezone.utc) - timedelta(hours=5))
    db.add(old)
    db.commit()
    s = jobs.Scheduler(factory=factory, eng=eng, fns=cycle_fns([]))
    s.start()
    assert s.thread.is_alive()
    s.stop(5)
    assert not s.thread.is_alive()
    db.refresh(old)
    assert old.status == "failed" and "interrupted" in old.error_message


def test_status_endpoint_reports_scheduler_jobs_failures_and_counts(env):
    client, db, factory, eng = env
    follow(client, accelerating_topic(db))
    jobs.run_cycle(factory=factory, eng=eng, fns=cycle_fns([], evidence=lambda d, c: (_ for _ in ()).throw(RuntimeError("evidence broke"))))
    s = client.get("/api/monitoring/status").json()
    assert s["scheduler"]["enabled"] is False and s["scheduler"]["state"] == "disabled" and s["monitored_trends"] == 1
    assert s["last_successful"]["detection"]["status"] == "completed" and s["last_successful"]["evidence"] is None
    assert s["last_cycle"]["status"] == "failed" and any("evidence broke" in (f["error"] or "") for f in s["latest_failures"])
    assert "token" not in str(s).lower()
    o = client.get("/api/monitoring/overview").json()
    assert o["followed"] == 1 and o["active_monitored"] == 1 and "latest_cycle" in o and "unread_notifications" in o


def test_internal_job_trigger_requires_token_and_reports_conflicts(env, monkeypatch):
    client, db, factory, eng = env
    monkeypatch.setitem(jobs.DEFAULT_FNS, "detection", lambda d, c: {"ran": True})
    monkeypatch.setattr(jobs, "engine", eng)  # the endpoint uses the module defaults: point them at the test database
    monkeypatch.setattr(jobs, "SessionLocal", factory)
    assert client.post("/api/internal/monitoring/run", json={"job": "detection"}).status_code in (401, 403)
    assert client.post("/api/internal/monitoring/run", json={"job": "detection"}, headers={"X-Internal-Token": "wrong"}).status_code in (401, 403)
    assert client.post("/api/internal/monitoring/run", json={"job": "bogus"}, headers=INTERNAL).status_code == 422
    r = client.post("/api/internal/monitoring/run", json={"job": "detection"}, headers=INTERNAL)
    assert r.status_code == 202 and r.json()["result"]["status"] == "completed"
    row = db.scalar(select(MonitoringJobRun).where(MonitoringJobRun.job_type == "detection"))
    assert row.trigger == "manual"
    with jobs.advisory_lock("detection", eng):
        assert client.post("/api/internal/monitoring/run", json={"job": "detection"}, headers=INTERNAL).status_code == 409
    assert INTERNAL["X-Internal-Token"] not in client.get("/api/monitoring/status").text


# ---------------------------------------------------------------- constraints + migration
def test_database_constraints_for_monitoring_tables(env):
    from sqlalchemy.exc import IntegrityError

    _, db, *_ = env
    t = mk_topic(db)
    db.add(TrendWatchlist(topic_id=t.id))
    db.commit()
    db.add(TrendWatchlist(topic_id=t.id))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(TrendWatchlist(topic_id=t.id, user_id=uuid.uuid4()))  # a different scope may follow the same topic
    db.commit()
    db.add(TrendEvent(topic_id=t.id, event_type="bogus", severity="important", title="x", detection_version="cd-1", deduplication_key="a"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(TrendEvent(topic_id=t.id, event_type="activity_spike", severity="important", title="x", detection_version="cd-1", deduplication_key="a"))
    db.commit()
    db.add(TrendEvent(topic_id=t.id, event_type="activity_spike", severity="important", title="y", detection_version="cd-1", deduplication_key="a"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    ev = db.scalar(select(TrendEvent))
    db.add(Notification(event_id=ev.id, severity="important"))
    db.commit()
    db.add(Notification(event_id=ev.id, severity="important"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.delete(ev)  # cascades to its notification
    db.commit()
    assert db.scalar(select(func.count()).select_from(Notification)) == 0


def test_migration_005_up_down_and_idempotent_with_create_all(engine):
    from app.core.database import Base

    env_ = {**os.environ, "DATABASE_URL": URL}
    alembic = lambda *a: subprocess.run([sys.executable, "-m", "alembic", *a], cwd=BACKEND, env=env_, capture_output=True, text=True)  # noqa: E731
    assert alembic("downgrade", "004").returncode == 0
    with engine.connect() as c:
        for t in ("trend_watchlist", "trend_events", "notifications", "monitoring_preferences", "monitoring_job_runs"):
            assert not c.execute(text(f"SELECT to_regclass('public.{t}')")).scalar()
        assert c.execute(text("SELECT to_regclass('public.research_dossiers')")).scalar()  # Phase 2 untouched
    Base.metadata.tables["trend_watchlist"].create(engine, checkfirst=True)  # what create_all may already have done
    r = alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    with engine.connect() as c:
        for t in ("trend_watchlist", "trend_events", "notifications", "monitoring_preferences", "monitoring_job_runs"):
            assert c.execute(text(f"SELECT to_regclass('public.{t}')")).scalar()
    assert alembic("upgrade", "head").returncode == 0
