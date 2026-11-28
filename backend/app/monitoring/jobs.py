"""Monitoring job execution: per-job PostgreSQL advisory locks, persisted job runs, retries, and the monitoring cycle.

Concurrency: before a job runs, a non-blocking session-level `pg_try_advisory_lock(key)` is taken on a dedicated
connection and held until the job ends. If another process/instance holds it, the job is recorded as 'skipped'.
(Session advisory locks need a direct or session-mode connection; they are not preserved by transaction-mode
poolers such as Supabase's pgbouncer on port 6543.)

Failure policy: collection failure -> detection still runs but with `collection_failed=True` (no inactivity/decline
events); recompute failure -> detection and evidence are skipped (never detect on incomplete observations);
detection/evidence failure -> previous events are untouched and the next cycle retries; a job is attempted at most
`monitoring_job_max_attempts` times per cycle, and a failed cycle waits for the next interval (no tight loops).
"""
import logging
import threading
import time
import uuid
import zlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.models import MonitoringJobRun, TrendEvent, TrendWatchlist, Topic
from app.monitoring import pipeline
from app.monitoring.config import DETECTION_VERSION
from app.services.trend_run_service import sanitize_error

log = logging.getLogger(__name__)
JOBS = ("collection", "recompute", "detection", "evidence", "notifications")


def lock_key(name: str) -> int:
    return zlib.crc32(f"tratepra.monitoring.{name}".encode())


@contextmanager
def advisory_lock(name: str, eng=None):
    """Yields True if the lock was acquired (and keeps it for the block), else False."""
    conn = (eng or engine).connect()
    got = False
    try:
        got = bool(conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": lock_key(name)}).scalar())
        conn.commit()
        yield got
    finally:
        try:
            if got:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key(name)})
                conn.commit()
        finally:
            conn.close()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ job bodies (each returns a details dict)
def collection_queries(db) -> list[str]:
    s = get_settings()
    qs = [q.strip()[:120] for q in s.monitoring_collection_queries.split(",") if q.strip()]
    rank = {"high": 0, "normal": 1, "low": 2}
    rows = db.execute(
        select(Topic.name, TrendWatchlist.priority).join(TrendWatchlist, TrendWatchlist.topic_id == Topic.id).where(TrendWatchlist.monitoring_enabled.is_(True))
    ).all()
    qs += [n[:120] for n, p in sorted(rows, key=lambda r: rank.get(r[1], 1))]
    return list(dict.fromkeys(qs))[: s.monitoring_collection_max_queries]


def job_collection(db, ctx: dict) -> dict:
    from app.ingestion.collector import collect
    from app.ingestion.embedding_store import embed_pending

    s = get_settings()
    queries = collection_queries(db)
    if not queries:
        return {"skipped": True, "reason": "no collection queries: nothing is followed and MONITORING_COLLECTION_QUERIES is empty"}
    per_query, any_ok, errors = {}, False, 0
    for q in queries:
        try:
            res = collect(db, q, None, s.monitoring_collection_time_range)
        except Exception as exc:  # one query failing must not stop the others
            db.rollback()
            errors += 1
            per_query[q] = {"error": sanitize_error(exc)}
            continue
        ok = [k for k, v in res.items() if v.get("status") == "ok"]
        any_ok |= bool(ok)
        per_query[q] = {"sources_ok": ok, "sources_failed": [k for k in res if k not in ok], "inserted": sum(v.get("inserted", 0) for v in res.values())}
    embedded = embed_pending(db) if any_ok else 0
    details = {"queries": per_query, "embedded": embedded, "any_source_ok": any_ok}
    ctx["collection_failed"] = not any_ok
    if not any_ok:
        raise RuntimeError("collection produced no successful source for any query")
    return details


def job_recompute(db, ctx: dict) -> dict:
    from app.ingestion.embedding_store import embed_pending
    from app.services.trend_run_service import recompute

    embed_pending(db)
    res = recompute(db)
    return {"run": {k: res.get(k) for k in ("run_id", "status", "documents_processed", "topics_discovered", "reused")}}


def job_detection(db, ctx: dict) -> dict:
    return pipeline.run_detection(db, collection_failed=bool(ctx.get("collection_failed")))


def job_evidence(db, ctx: dict) -> dict:
    return pipeline.run_evidence_association(db)


def job_notifications(db, ctx: dict) -> dict:
    return pipeline.prepare_notifications(db)


DEFAULT_FNS = {"collection": job_collection, "recompute": job_recompute, "detection": job_detection, "evidence": job_evidence, "notifications": job_notifications}


# ------------------------------------------------------------------ runner
def run_job(name: str, *, trigger: str = "scheduled", cycle_id=None, ctx: dict | None = None, factory=None, eng=None, fns=None) -> dict:
    """Run one job under its advisory lock, with a persisted JobRun. Returns {"status", "job_run_id", "details", "error"}."""
    s = get_settings()
    factory, fns, ctx = factory or SessionLocal, fns or DEFAULT_FNS, ctx if ctx is not None else {}
    with advisory_lock(name, eng) as got:
        with factory() as db:
            row = MonitoringJobRun(job_type=name, trigger=trigger, cycle_id=cycle_id, status="running" if got else "skipped", started_at=_utcnow())
            if not got:
                row.completed_at, row.duration_ms = _utcnow(), 0
                row.details = {"reason": "another instance is already running this job"}
            db.add(row)
            db.commit()
            rid = row.id
        if not got:
            return {"status": "skipped", "job_run_id": str(rid), "details": {"reason": "locked"}, "error": None}
        t0, err, details, status = time.monotonic(), None, {}, "failed"
        for attempt in range(1, max(1, s.monitoring_job_max_attempts) + 1):
            try:
                with factory() as db:
                    details = fns[name](db, ctx) or {}
                status, err = ("skipped" if details.get("skipped") else "completed"), None
                break
            except Exception as exc:
                log.exception("monitoring job %s failed (attempt %s)", name, attempt)
                err = sanitize_error(exc)
                with factory() as db:
                    db.execute(update(MonitoringJobRun).where(MonitoringJobRun.id == rid).values(attempt=attempt))
                    db.commit()
                if attempt < s.monitoring_job_max_attempts:
                    time.sleep(s.monitoring_job_retry_delay_seconds)
        with factory() as db:
            db.execute(update(MonitoringJobRun).where(MonitoringJobRun.id == rid).values(
                status=status, completed_at=_utcnow(), duration_ms=int((time.monotonic() - t0) * 1000), details=details, error_message=err))
            db.commit()
        return {"status": status, "job_run_id": str(rid), "details": details, "error": err}


def _failure_event(factory, cycle_id, job: str, error: str | None) -> None:
    """Persist a monitoring_failure event so the user learns that monitoring needs attention."""
    from app.monitoring.detection import EventCandidate
    from app.monitoring.config import MonitoringConfig

    c = EventCandidate(event_type="monitoring_failure", severity="important", title=f"Monitoring job failed: {job}", topic_id="",
                       dedup_key=f"cycle:{cycle_id}:{job}", details={"job": job, "error": error, "topic": "Monitoring"})
    c.explanation = ""
    with factory() as db:
        now = _utcnow()
        db.execute(pg_insert(TrendEvent).values(
            id=uuid.uuid4(), topic_id=None, event_type=c.event_type, severity="important", title=c.title,
            description=f"The {job} job failed and was not completed: {error or 'unknown error'}. Previous trend history and events are unchanged.",
            explanation=f"The {job} job failed and was not completed: {error or 'unknown error'}. Previous trend history and events are unchanged. "
                        "No inactivity or decline events are raised for a failed collection.",
            details=c.details, detection_version=DETECTION_VERSION, deduplication_key=c.dedup_key, detected_at=now,
        ).on_conflict_do_nothing(index_elements=["deduplication_key"]))
        db.commit()


def run_cycle(*, trigger: str = "scheduled", factory=None, eng=None, fns=None, stop: threading.Event | None = None) -> dict:
    """collection -> recompute -> detection -> evidence -> notifications, each its own job. Never raises."""
    factory = factory or SessionLocal
    cycle_id = uuid.uuid4()
    with advisory_lock("cycle", eng) as got:
        with factory() as db:
            row = MonitoringJobRun(id=cycle_id, cycle_id=cycle_id, job_type="cycle", trigger=trigger, status="running" if got else "skipped", started_at=_utcnow())
            if not got:
                row.completed_at, row.duration_ms, row.details = _utcnow(), 0, {"reason": "another cycle is already running"}
            db.add(row)
            db.commit()
        if not got:
            return {"status": "skipped", "cycle_id": str(cycle_id)}
        t0, ctx, results, failed = time.monotonic(), {}, {}, []
        for name in JOBS:
            if stop is not None and stop.is_set():
                results[name] = {"status": "skipped", "details": {"reason": "shutdown requested"}}
                continue
            if name in ("detection", "evidence") and results.get("recompute", {}).get("status") == "failed":
                results[name] = {"status": "skipped", "details": {"reason": "trend recomputation failed; not detecting on incomplete observations"}}
                continue
            if name == "notifications" and failed:
                for f in failed:
                    _failure_event(factory, cycle_id, f, results[f].get("error"))
            r = run_job(name, trigger=trigger, cycle_id=cycle_id, ctx=ctx, factory=factory, eng=eng, fns=fns)
            results[name] = r
            if r["status"] == "failed":
                failed.append(name)
        status = "failed" if failed else "completed"
        with factory() as db:
            db.execute(update(MonitoringJobRun).where(MonitoringJobRun.id == cycle_id).values(
                status=status, completed_at=_utcnow(), duration_ms=int((time.monotonic() - t0) * 1000),
                details={"jobs": {k: v["status"] for k, v in results.items()}, "failed": failed},
                error_message=("; ".join(f"{f}: {results[f].get('error')}" for f in failed) or None)))
            db.commit()
        return {"status": status, "cycle_id": str(cycle_id), "jobs": {k: v["status"] for k, v in results.items()}}


# ------------------------------------------------------------------ scheduler
def recover_interrupted(factory=None) -> int:
    """Rows still 'running' after the timeout belong to a crashed process (its advisory lock died with it)."""
    s = get_settings()
    with (factory or SessionLocal)() as db:
        res = db.execute(update(MonitoringJobRun).where(
            MonitoringJobRun.status == "running", MonitoringJobRun.started_at < _utcnow() - timedelta(minutes=s.monitoring_running_timeout_minutes)
        ).values(status="failed", completed_at=_utcnow(), error_message="interrupted: the process stopped before the job finished"))
        db.commit()
        return res.rowcount


def next_due(factory=None, started_at: datetime | None = None) -> datetime:
    """Next cycle time = last cycle start (persisted) + interval; falls back to scheduler start + interval."""
    s = get_settings()
    with (factory or SessionLocal)() as db:
        last = db.scalar(select(MonitoringJobRun.started_at).where(MonitoringJobRun.job_type == "cycle", MonitoringJobRun.status != "skipped")
                         .order_by(MonitoringJobRun.started_at.desc()).limit(1))
    base = last or started_at or _utcnow()
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base + timedelta(minutes=s.monitoring_interval_minutes)


class Scheduler:
    """One background thread; on every tick checks whether a cycle is due. Stoppable and restart-safe."""

    def __init__(self, factory=None, eng=None, fns=None):
        self.factory, self.eng, self.fns = factory, eng, fns
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.started_at = _utcnow()
        self.running_cycle = False

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        try:
            n = recover_interrupted(self.factory)
            if n:
                log.warning("marked %s interrupted monitoring job(s) as failed", n)
        except Exception:
            log.exception("monitoring recovery failed")
        self.stop_event.clear()
        self.started_at = _utcnow()
        self.thread = threading.Thread(target=self._loop, name="monitoring-scheduler", daemon=True)
        self.thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout)

    def tick(self) -> bool:
        """Run a cycle if due. Returns True if one was started."""
        if next_due(self.factory, self.started_at) > _utcnow():
            return False
        self.running_cycle = True
        try:
            run_cycle(trigger="scheduled", factory=self.factory, eng=self.eng, fns=self.fns, stop=self.stop_event)
        finally:
            self.running_cycle = False
        return True

    def _loop(self) -> None:
        tick = max(1, get_settings().monitoring_tick_seconds)
        while not self.stop_event.wait(tick):
            try:
                self.tick()
            except Exception:
                log.exception("monitoring scheduler tick failed")  # never kill the loop; next tick retries after the interval


scheduler: Scheduler | None = None


def start_scheduler() -> None:
    global scheduler
    if get_settings().monitoring_scheduler_enabled and scheduler is None:
        scheduler = Scheduler()
        scheduler.start()


def stop_scheduler() -> None:
    global scheduler
    if scheduler is not None:
        scheduler.stop()
        scheduler = None
