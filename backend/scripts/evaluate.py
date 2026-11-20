"""Run the evaluation datasets and print a JSON report.

Usage: python -m scripts.evaluate [--k 5]
 - trend lifecycle cases (synthetic regression check; always runs)
 - retrieval metrics for labelled queries in data/evaluation/research_queries.json (needs DB with collected data)
Unlabelled queries are reported as skipped, never scored.
"""
import argparse
import json
from pathlib import Path

from app.evaluation.retrieval import aggregate, evaluate_query
from app.evaluation.trend_quality import lifecycle_accuracy

DATA = Path(__file__).resolve().parents[2] / "data" / "evaluation"


def run_retrieval(k: int) -> dict:
    spec = json.loads((DATA / "research_queries.json").read_text())["queries"]
    labelled = [q for q in spec if q["relevant_urls"]]
    skipped = [q["query"] for q in spec if not q["relevant_urls"]]
    if not labelled:
        return {"status": "no_labelled_queries", "skipped_unlabelled": skipped}
    from app.core.database import SessionLocal
    from app.research.query_processor import process_query
    from app.research.ranker import rank
    from app.research.retriever import retrieve
    from app.connectors.base import parse_time_range

    rows = []
    with SessionLocal() as db:
        for q in labelled:
            pq = process_query(q["query"], q["time_range"])
            cands = retrieve(db, pq.cleaned, ["google_news", "youtube", "reddit"], pq.time_range, keywords=pq.keywords, phrases=pq.phrases)
            window = max(parse_time_range(pq.time_range).total_seconds() / 86400, 1)
            ranked = [r.candidate.document.url for r in rank(cands, pq.keywords, window, phrases=pq.phrases)]
            rows.append(evaluate_query(ranked, set(q["relevant_urls"]), k))
    return {"status": "ok", "metrics": aggregate(rows), "skipped_unlabelled": skipped}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--k", type=int, default=5)
    args = p.parse_args()
    cases = json.loads((DATA / "trend_cases.json").read_text())["cases"]
    report = {"lifecycle_synthetic": lifecycle_accuracy(cases), "retrieval": run_retrieval(args.k)}
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
