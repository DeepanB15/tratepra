"""TrendRun lifecycle, idempotency, failure safety, continuity, freshness and constraints on real PostgreSQL."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import Topic, TrendObservation, TrendRun
from app.services import trend_service
from app.services.trend_run_service import recompute

from .helpers import NOW, add_docs, keyword_fit, seed_three_clusters


def _counts(db):
    db.expire_all()
    return {
        "runs": db.scalar(select(func.count(TrendRun.id))),
        "obs": db.scalar(select(func.count(TrendObservation.id))),
        "topics": db.scalar(select(func.count(Topic.id))),
    }


def test_run_is_persisted_and_observations_link_to_it(db):
    seed_three_clusters(db)
    r = recompute(db, as_of=NOW, fit=keyword_fit())
    assert r["status"] == "ok" and r["topics"] == 3 and r["new_topics"] == 3
    run = db.get(TrendRun, r["run_id"])
    assert run.status == "completed" and run.completed_at and run.started_at
    assert (run.documents_available, run.documents_processed, run.documents_rejected) == (30, 30, 0)
    assert run.topics_discovered == 3 and run.topics_created == 3 and run.topics_matched == 0
    assert run.model_version.startswith("bertopic+") and run.formula_version and run.configuration["embedding_dim"] == 384
    assert run.diagnostics["topic_quality"]["noise_percentage"] == 0.0
    obs = db.scalars(select(TrendObservation)).all()
    assert len(obs) == 3 and {o.run_id for o in obs} == {run.id}
    for t in db.scalars(select(Topic)):
        assert t.last_run_id == run.id and t.last_observed_at == run.completed_at and t.name_confidence is not None


def test_identical_rerun_is_idempotent_and_appends_nothing(db):
    seed_three_clusters(db)
    first = recompute(db, as_of=NOW, fit=keyword_fit())
    before = _counts(db)
    again = recompute(db, as_of=NOW + timedelta(hours=3), fit=keyword_fit())  # same UTC day, same data
    assert again["status"] == "unchanged" and again["run_id"] == first["run_id"] and again["run_key"] == first["run_key"]
    assert _counts(db) == before


def test_changed_dataset_creates_new_run_and_keeps_topic_identity_and_history(db):
    seed_three_clusters(db)
    first = recompute(db, as_of=NOW, fit=keyword_fit())
    ids_before = {t.name: t.id for t in db.scalars(select(Topic))}
    add_docs(db, "kubernetes", 6)  # genuinely new data
    second = recompute(db, as_of=NOW, fit=keyword_fit())
    assert second["status"] == "ok" and second["run_id"] != first["run_id"]
    assert second["matched_topics"] == 3 and second["new_topics"] == 0
    assert {t.name: t.id for t in db.scalars(select(Topic))} == ids_before  # continuity: same ids, no duplicates
    k = db.scalar(select(Topic).where(Topic.name.ilike("kubernetes%")))
    hist = trend_service.trend_history(db, str(k.id))
    assert len(hist) == 2 and len({h["run_id"] for h in hist}) == 2 and all(h["legacy"] is False for h in hist)
    assert hist[0]["document_volume"] == 10 and hist[1]["document_volume"] == 16  # previous history preserved
    ident = db.get(TrendRun, second["run_id"]).diagnostics["identity"]
    assert ident["outcomes"]["matched"] == 3 and ident["model_version_changed"] is False


def test_next_day_with_same_documents_is_a_new_run(db):
    seed_three_clusters(db)
    a = recompute(db, as_of=NOW, fit=keyword_fit())
    b = recompute(db, as_of=NOW + timedelta(days=1), fit=keyword_fit())
    assert a["run_id"] != b["run_id"] and b["status"] == "ok"
    for t in db.scalars(select(Topic)):
        assert db.scalar(select(func.count(TrendObservation.id)).where(TrendObservation.topic_id == t.id)) == 2


def test_failed_run_does_not_corrupt_previous_results_or_topic_state(db):
    seed_three_clusters(db)
    ok = recompute(db, as_of=NOW, fit=keyword_fit())
    add_docs(db, "rust", 5)
    before = _counts(db)
    snap = {t.id: (t.last_run_id, t.last_observed_at, t.name) for t in db.scalars(select(Topic))}

    def boom(texts, emb, min_topic_size=None):
        raise RuntimeError("model exploded postgresql://user:s3cret@db.example.com/x")

    with pytest.raises(RuntimeError):
        recompute(db, as_of=NOW, fit=boom)
    db.expire_all()
    after = _counts(db)
    assert after["obs"] == before["obs"] and after["topics"] == before["topics"] and after["runs"] == before["runs"] + 1
    failed = db.scalars(select(TrendRun).where(TrendRun.status == "failed")).one()
    assert "s3cret" not in failed.error_message and failed.completed_at is None
    assert {t.id: (t.last_run_id, t.last_observed_at, t.name) for t in db.scalars(select(Topic))} == snap
    # failed run did not make anything stale/inactive
    ov = trend_service.discovery_overview(db)
    assert ov["total_active_trends"] == 3 and ov["stale_trends"] == 0
    assert ov["latest_run_status"] == "failed" and ov["latest_successful_run"]["run_id"] == ok["run_id"]

    # retrying the same logical run succeeds and reuses the failed row
    retry = recompute(db, as_of=NOW, fit=keyword_fit())
    assert retry["status"] == "ok" and retry["run_id"] == str(failed.id)
    assert db.get(TrendRun, failed.id).diagnostics["attempts"] == 2


def test_running_run_blocks_duplicate_execution_until_it_times_out(db):
    from datetime import datetime, timezone

    seed_three_clusters(db)
    key = recompute(db, as_of=NOW, dry_run=True, fit=keyword_fit())["run_key"]
    run = TrendRun(run_key=key, status="running", started_at=datetime.now(timezone.utc))  # another worker mid-run
    db.add(run)
    db.commit()
    assert recompute(db, as_of=NOW, fit=keyword_fit())["status"] == "already_running"
    assert _counts(db)["obs"] == 0
    run.started_at = datetime.now(timezone.utc) - timedelta(hours=5)  # crashed worker: past the timeout
    db.commit()
    r = recompute(db, as_of=NOW, fit=keyword_fit())
    assert r["status"] == "ok" and r["run_id"] == str(run.id) and _counts(db)["obs"] == 3


def test_insufficient_and_empty_inputs_are_recorded_not_hidden(db):
    r0 = recompute(db, as_of=NOW, fit=keyword_fit())
    assert r0["status"] == "no_documents"
    add_docs(db, "rust", 8)
    r1 = recompute(db, as_of=NOW, fit=keyword_fit())
    assert r1["status"] == "insufficient_documents" and r1["topics"] == 0
    runs = db.scalars(select(TrendRun).order_by(TrendRun.created_at)).all()
    assert [x.status for x in runs] == ["failed", "failed"]
    assert "insufficient_documents" in runs[1].error_message
    assert _counts(db)["topics"] == 0


def test_all_noise_is_reported_as_no_topics_found(db):
    seed_three_clusters(db)
    r = recompute(db, as_of=NOW, fit=keyword_fit(drop=("kubernetes", "rust", "solar")))
    assert r["status"] == "no_topics_found" and r["noise_documents"] == 30
    assert _counts(db)["topics"] == 0


def test_rejections_are_recorded_with_reasons_in_run_diagnostics(db):
    seed_three_clusters(db)
    add_docs(db, "rust", 3, model="some-other-embedding-model")
    r = recompute(db, as_of=NOW, fit=keyword_fit())
    prep = db.get(TrendRun, r["run_id"]).diagnostics["prep"]
    assert prep["reasons"]["embedding_model_mismatch"] == 3 and prep["rejected"] == 3
    assert db.get(TrendRun, r["run_id"]).documents_rejected == 3
    assert prep["input"] == prep["kept"] + prep["rejected"]


def test_noise_documents_stay_identifiable(db):
    seed_three_clusters(db)
    r = recompute(db, as_of=NOW, fit=keyword_fit(drop=("solar",)))
    run = db.get(TrendRun, r["run_id"])
    assert run.noise_documents == 10 and run.topics_discovered == 2
    assert run.diagnostics["topic_quality"]["noise_percentage"] == pytest.approx(33.33, abs=0.01)
    assert run.diagnostics["topic_quality"]["per_source"]["google_news"]["noise"] == 10


def test_dry_run_writes_nothing(db):
    seed_three_clusters(db)
    r = recompute(db, as_of=NOW, dry_run=True, fit=keyword_fit())
    assert r["status"] == "dry_run" and r["topics"] == 3 and len(r["topic_details"]) == 3 and r["run_key"]
    assert _counts(db) == {"runs": 0, "obs": 0, "topics": 0}


def test_absent_topics_become_stale_then_inactive_and_leave_default_discovery(db):
    seed_three_clusters(db)
    recompute(db, as_of=NOW, fit=keyword_fit())
    assert len(trend_service.list_trends(db)) == 3
    for day in range(1, 5):  # four later completed runs in which "solar" is not discovered
        recompute(db, as_of=NOW + timedelta(days=day), fit=keyword_fit(drop=("solar",)))
        states = {r["topic_name"].split()[0]: r["activity_state"] for r in trend_service.search_trends(db, activity_state=None)[0]}
        if day == 1:
            assert states["Solar"] == "stale" and states["Kubernetes"] == "active"
    assert states["Solar"] == "inactive"
    assert {r["topic_name"].split()[0] for r in trend_service.list_trends(db)} == {"Kubernetes", "Rust"}
    assert [r["topic_name"].split()[0] for r in trend_service.search_trends(db, activity_state="inactive")[0]] == ["Solar"]
    ov = trend_service.discovery_overview(db)
    assert ov["total_active_trends"] == 2 and ov["inactive_trends"] == 1


def test_timezone_aware_windows_and_ist_as_of(db):
    from datetime import datetime, timezone

    seed_three_clusters(db)
    ist = timezone(timedelta(hours=5, minutes=30))
    r = recompute(db, as_of=datetime(2026, 11, 20, 20, 0, tzinfo=ist), fit=keyword_fit())  # 14:30 UTC -> same UTC day as NOW
    run = db.get(TrendRun, r["run_id"])
    assert run.window_end == datetime(2026, 11, 21, tzinfo=timezone.utc)
    o = db.scalars(select(TrendObservation)).first()
    assert o.window_end.tzinfo is not None and o.window_end == run.window_end


def test_potential_split_is_recorded_not_silently_matched(db):
    """A stored topic that two new topics resemble: one inherits the id, the other is flagged and gets a NEW id."""
    seed_three_clusters(db)
    recompute(db, as_of=NOW, fit=keyword_fit())
    rust = db.scalar(select(Topic).where(Topic.name.ilike("rust%")))
    # Make the stored 'solar' topic's centroid look like a blend of rust and solar so the next run sees a split-like geometry
    solar = db.scalar(select(Topic).where(Topic.name.ilike("solar%")))
    rust_c = list(map(float, rust.embedding))
    solar.embedding = [0.5 * a + 0.5 * b for a, b in zip(rust_c, map(float, solar.embedding))]
    db.commit()
    add_docs(db, "rust", 4)
    r = recompute(db, as_of=NOW, fit=keyword_fit())
    decisions = db.get(TrendRun, r["run_id"]).diagnostics["identity"]["decisions"]
    outcomes = {d["outcome"] for d in decisions}
    assert outcomes <= {"matched", "potential_merge", "potential_split", "uncertain", "new"}
    assert all(d["matched_topic_id"] is None for d in decisions if d["outcome"] in ("potential_split", "uncertain", "new"))
    assert len({d["matched_topic_id"] for d in decisions if d["matched_topic_id"]}) == len([d for d in decisions if d["matched_topic_id"]])  # one-to-one


# ---------------------------------------------------------------- constraints
def test_database_constraints(db):
    db.add(TrendRun(run_key="k1", status="completed"))
    db.commit()
    db.add(TrendRun(run_key="k1", status="completed"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(TrendRun(run_key="k2", status="bogus"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    run = TrendRun(run_key="k3", status="completed")
    t = Topic(name="T", terms=[], model_version="m", run_id="r")
    db.add_all([run, t])
    db.commit()

    def obs(run_id):
        return TrendObservation(topic_id=t.id, run_id=run_id, window_start=NOW, window_end=NOW, document_volume=1, formula_version="f", model_version="m")

    db.add(obs(run.id))
    db.commit()
    db.add(obs(run.id))  # same topic + same run: rejected
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add_all([obs(None), obs(None)])  # legacy rows (no run) are not constrained
    db.commit()
    assert db.scalar(select(func.count(TrendObservation.id))) == 3


def test_migration_003_backfills_and_preserves_legacy_history(engine):
    """Downgrade to 002, insert legacy rows, upgrade: rows survive, last_observed_at is backfilled, run_id stays NULL."""
    import os
    import subprocess
    import sys

    from .conftest import BACKEND, URL

    env = {**os.environ, "DATABASE_URL": URL}
    alembic = lambda *a: subprocess.run([sys.executable, "-m", "alembic", *a], cwd=BACKEND, env=env, capture_output=True, text=True)
    with engine.begin() as c:
        c.execute(text("TRUNCATE topics, trend_runs CASCADE"))
    r = alembic("downgrade", "002")
    assert r.returncode == 0, r.stderr
    with engine.begin() as c:
        tid = c.execute(text("INSERT INTO topics (id,name,terms,model_version,run_id,created_at,updated_at) VALUES (gen_random_uuid(),'Legacy','[]','m','r',now(),now()) RETURNING id")).scalar()
        for i in range(2):
            c.execute(text(
                "INSERT INTO trend_observations (id,topic_id,window_start,window_end,document_volume,coverage,raw_signals,formula_version,model_version,created_at) "
                "VALUES (gen_random_uuid(),:t,now(),now(),3,'{}','{}','f','m', now() - make_interval(days => :d))"), {"t": tid, "d": i})
    r = alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM trend_observations WHERE run_id IS NULL")).scalar() == 2
        row = c.execute(text("SELECT last_observed_at, last_run_id, needs_review FROM topics")).one()
        assert row[0] is not None and row[1] is None and row[2] is False


def test_migration_003_is_idempotent_when_create_all_already_made_trend_runs(engine):
    """AUTO_CREATE_TABLES=true creates the trend_runs table (but no new columns) before `alembic upgrade head`."""
    import os
    import subprocess
    import sys

    from app.core.database import Base
    from .conftest import BACKEND, URL

    env = {**os.environ, "DATABASE_URL": URL}
    alembic = lambda *a: subprocess.run([sys.executable, "-m", "alembic", *a], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert alembic("downgrade", "002").returncode == 0
    Base.metadata.tables["trend_runs"].create(engine, checkfirst=True)  # what create_all would have done
    r = alembic("upgrade", "head")
    assert r.returncode == 0, r.stderr
    with engine.connect() as c:
        cols = {row[0] for row in c.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='topics'"))}
        assert {"last_run_id", "last_observed_at", "needs_review"} <= cols
    assert alembic("upgrade", "head").returncode == 0  # re-running is a no-op
