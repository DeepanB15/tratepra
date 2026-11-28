"""Change-detection evaluation on SYNTHETIC controlled cases (expected outputs written from the written rules, not
from the detector's output). Pure: no DB. Results describe rule behaviour on constructed inputs only; they say nothing
about accuracy on real trends."""
from datetime import datetime, timedelta, timezone

from app.monitoring.config import MonitoringConfig
from app.monitoring.detection import detect
from app.monitoring.snapshots import Snapshot

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


def build_snapshots(specs: list[dict]) -> list[Snapshot]:
    out = []
    for i, s in enumerate(specs):
        end = T0 + timedelta(days=7 * s.get("i", i))
        out.append(Snapshot(
            observation_id=f"o{i}", run_id=f"r{i}", topic_id="t", observed_at=end, window_start=end - timedelta(days=s.get("days", 14)), window_end=end,
            trend_score=s.get("score", 50.0), score_coverage=0.9, growth=s.get("growth"), momentum_pp=None, momentum_direction=None, novelty=None,
            document_volume=s.get("vol", 20), sources=s.get("sources", 3), lifecycle=s.get("lifecycle", "growing"),
            formula_version=s.get("formula", "v1.0"), model_version="m"))
    return out


def run_case(case: dict, cfg: MonitoringConfig | None = None) -> dict:
    cfg = cfg or MonitoringConfig()
    d = detect(build_snapshots(case["snapshots"]), cfg, topic_name="case", collection_failed=case.get("collection_failed", False),
               activity=case.get("activity"), is_new_topic=case.get("is_new_topic", False))
    got = sorted({e.event_type for e in d.events})
    exp = sorted(case["expected"])
    return {"id": case["id"], "category": case["category"], "expected": exp, "got": got, "passed": got == exp,
            "suppressed": [s.get("reason") for s in d.suppressed]}


def evaluate(cases: list[dict], cfg: MonitoringConfig | None = None) -> dict:
    results = [run_case(c, cfg) for c in cases]
    tp = sum(len(set(r["got"]) & set(r["expected"])) for r in results)
    fp = sum(len(set(r["got"]) - set(r["expected"])) for r in results)
    fn = sum(len(set(r["expected"]) - set(r["got"])) for r in results)
    return {
        "label": "synthetic controlled cases", "cases": len(results), "passed": sum(r["passed"] for r in results),
        "event_precision": round(tp / (tp + fp), 3) if tp + fp else None, "event_recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "true_positives": tp, "false_positives": fp, "false_negatives": fn,
        "false_positive_cases": [r["id"] for r in results if set(r["got"]) - set(r["expected"])],
        "missed_cases": [r["id"] for r in results if set(r["expected"]) - set(r["got"])], "results": results,
    }


def replay_history(db, cfg: MonitoringConfig | None = None, limit_topics: int = 500) -> dict:
    """Historical replay: for every topic, run the detector over each chronological prefix of its completed-run snapshots.
    Read-only and counts only: with no labelled ground truth this reports volume/behaviour, NOT accuracy."""
    from collections import Counter

    from sqlalchemy import select

    from app.models import Topic
    from app.monitoring.snapshots import load_snapshots

    cfg = cfg or MonitoringConfig()
    counts, suppressed, topics, steps = Counter(), Counter(), 0, 0
    for t in db.scalars(select(Topic).limit(limit_topics)):
        hist = load_snapshots(db, t.id)
        if len(hist) < 2:
            continue
        topics += 1
        for k in range(2, len(hist) + 1):
            steps += 1
            d = detect(hist[:k], cfg, topic_name=t.name)
            counts.update(e.event_type for e in d.events)
            suppressed.update(s.get("reason", "?") for s in d.suppressed)
    return {"label": "historical replay (counts only, no accuracy claim)", "topics_with_history": topics, "comparisons": steps,
            "events_by_type": dict(counts), "suppressed_by_reason": dict(suppressed)}
