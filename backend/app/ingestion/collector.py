"""Shared ingestion pipeline: parallel fetch -> date filter -> normalize -> dedupe -> persist.

Network I/O runs in a thread pool (one task per connector). Database writes happen afterwards on
the calling thread, because SQLAlchemy sessions are not thread-safe. One failing connector never
blocks the others; every failure is returned in that source's status and logged.
"""
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import CONNECTOR_CLASSES, get_connector
from app.core.exceptions import ConnectorError
from app.ingestion.deduplicator import dedupe_batch, filter_existing
from app.ingestion.filters import filter_by_date
from app.ingestion.normalizer import normalize_record, validation_error
from app.models import CollectionLog, Document, Source

log = logging.getLogger(__name__)

# Google Trends rows are search-interest observations, not text documents. They are
# stored (for the search-interest signal) but excluded from retrieval and topic modeling.
NON_TEXT_SOURCES = {"google_trends"}
MAX_WORKERS = 4


@dataclass
class FetchOutcome:
    source: str
    records: list[dict] = field(default_factory=list)
    status: str = "ok"  # ok | error | quota | rate_limit | auth | unavailable
    error: str | None = None
    duration_ms: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fetch_one(key: str, query: str, time_range: str) -> FetchOutcome:
    started, started_at = time.time(), _now()

    def done(records, status="ok", error=None) -> FetchOutcome:
        return FetchOutcome(key, records, status, error, int((time.time() - started) * 1000), started_at, _now())

    try:
        return done(get_connector(key).search(query, time_range))
    except ConnectorError as exc:
        return done([], exc.kind, exc.message)
    except Exception as exc:  # unexpected provider/parse failure: record, don't hide
        log.exception("Connector %s failed", key)
        return done([], "error", str(exc))


def fetch_sources(keys: list[str], query: str, time_range: str, max_workers: int = MAX_WORKERS) -> dict[str, FetchOutcome]:
    """Run the selected connectors concurrently. Result order follows `keys`."""
    keys = [k for k in dict.fromkeys(keys) if k in CONNECTOR_CLASSES]
    if not keys:
        return {}
    outcomes: dict[str, FetchOutcome] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(keys))) as pool:
        futures = {pool.submit(_fetch_one, k, query, time_range): k for k in keys}
        for fut in as_completed(futures):
            outcomes[futures[fut]] = fut.result()
    return {k: outcomes[k] for k in keys}


def persist_outcome(db: Session, outcome: FetchOutcome, query: str, time_range: str, run_id: str = "") -> dict[str, Any]:
    """Filter, normalize, dedupe and store one source's records. Never raises."""
    key = outcome.source
    source = db.scalar(select(Source).where(Source.key == key))
    status: dict[str, Any] = {
        "run_id": run_id,
        "source": key,
        "status": outcome.status,
        "error": outcome.error,
        "fetched": len(outcome.records),
        "inserted": 0,
        "duplicates": 0,
        "out_of_window": 0,
        "undated": 0,
        "rejected": 0,
        "duration_ms": outcome.duration_ms,
        "started_at": outcome.started_at,
        "completed_at": outcome.completed_at,
    }
    if outcome.status == "ok" and source is not None:
        try:
            normalized = []
            for r in outcome.records:
                doc = normalize_record(r)
                reason = validation_error(doc)
                if reason:
                    status["rejected"] += 1
                    log.warning("Rejected %s record: %s", key, reason)
                else:
                    normalized.append(doc)
            filtered = filter_by_date(normalized, time_range)
            status["out_of_window"], status["undated"] = filtered.out_of_window, filtered.undated
            docs = dedupe_batch(filtered.kept)
            new_docs, dup = filter_existing(db, docs)
            status["duplicates"] = dup + (len(filtered.kept) - len(docs))
            for d in new_docs:
                db.add(
                    Document(
                        source_id=source.id,
                        external_id=d["external_id"],
                        title=d["title"],
                        description=d["description"],
                        normalized_text=d["normalized_text"],
                        url=d["url"],
                        canonical_url=d["canonical_url"],
                        content_hash=d["content_hash"],
                        published_at=d["published_at"],
                        collected_at=d["collected_at"] or datetime.now(timezone.utc),
                        engagement=d["engagement"],
                        metadata_=d["metadata"],
                    )
                )
            status["inserted"] = len(new_docs)
            db.commit()
        except Exception as exc:
            db.rollback()
            log.exception("Persisting %s failed", key)
            status.update(status="error", error=f"Persistence failed: {exc}", inserted=0)

    if source is not None:
        source.last_status = status["status"]
        source.last_error = status["error"]
        source.last_run_at = datetime.now(timezone.utc)
    db.add(
        CollectionLog(
            run_id=run_id,
            source_key=key,
            query=query,
            status=status["status"],
            fetched=status["fetched"],
            inserted=status["inserted"],
            duplicates=status["duplicates"],
            out_of_window=status["out_of_window"],
            undated=status["undated"],
            rejected=status["rejected"],
            error=status["error"],
            duration_ms=status["duration_ms"],
            started_at=outcome.started_at,
            completed_at=outcome.completed_at,
        )
    )
    db.commit()
    return status


def collect(db: Session, query: str, sources: list[str] | None, time_range: str = "30d") -> dict[str, dict[str, Any]]:
    keys = sources or list(CONNECTOR_CLASSES)
    run_id = str(uuid.uuid4())
    outcomes = fetch_sources(keys, query, time_range)
    return {k: persist_outcome(db, o, query, time_range, run_id) for k, o in outcomes.items()}


def collect_source(db: Session, source_key: str, query: str, time_range: str) -> dict[str, Any]:
    return collect(db, query, [source_key], time_range).get(source_key, {"source": source_key, "status": "error", "error": "Unknown source"})
