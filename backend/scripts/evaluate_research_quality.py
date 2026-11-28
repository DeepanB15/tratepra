"""Research quality evaluation (Phase 2).

  python -m scripts.evaluate_research_quality --init            write a template of candidate questions from stored topics
  python -m scripts.evaluate_research_quality [--k 5] [--dossiers]   score labelled cases in data/evaluation/research_eval.json

A case is scored only if a human labelled it (`relevant_urls` non-empty, or `expect_insufficient`/`expect_contradiction`).
Unlabelled cases are listed as skipped - there is no default score. Retrieval is scored with the production hybrid
retriever + ranker + evidence selection against the configured database. `--dossiers` also generates a dossier per case
(real LLM if reachable) and reports claim-level metrics. Nothing is written to the database except dossier rows when
--dossiers is used.
"""
import argparse
import json
from pathlib import Path

from app.evaluation.research_quality import diversity, dossier_metrics, duplicate_rate, mean_of
from app.evaluation.retrieval import aggregate, evaluate_query

DATA = Path(__file__).resolve().parents[2] / "data" / "evaluation"
FILE = DATA / "research_eval.json"
TYPES = {
    "factual": "What is {t}?",
    "trend_explanation": "Why is {t} gaining attention?",
    "comparative": "How does {t} compare with related developments?",
    "time_based": "What changed about {t} in the last 7 days?",
    "entity": "Which organisations are involved in {t}?",
    "insufficient_evidence": "What is the market share of {t} in Antarctica?",
    "contradictory": "Is there disagreement about {t}?",
}


def init_template(n_topics: int = 5) -> dict:
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models import Topic

    cases = []
    with SessionLocal() as db:
        topics = db.scalars(select(Topic).order_by(Topic.last_observed_at.desc().nullslast()).limit(n_topics)).all()
        for t in topics:
            for kind, tmpl in TYPES.items():
                cases.append({"type": kind, "topic_id": str(t.id), "query": tmpl.format(t=t.name), "time_range": "30d",
                              "relevant_urls": [], "expect_insufficient": kind == "insufficient_evidence" or None,
                              "expect_contradiction": None, "expected_gaps": [], "reviewed_by": None})
    FILE.write_text(json.dumps({"instructions": "Label by reading stored documents. Fill relevant_urls (URLs of documents that truly answer the query), expected_gaps (codes) and reviewed_by. Unlabelled cases are never scored.", "cases": cases}, indent=2))
    return {"status": "template_written", "path": str(FILE), "cases": len(cases)}


def run(k: int, with_dossiers: bool, file: Path = FILE) -> dict:
    from app.connectors.base import parse_time_range
    from app.core.database import SessionLocal
    from app.research.context_builder import select_evidence
    from app.research.excerpts import publisher_of
    from app.research.query_processor import process_query
    from app.research.ranker import rank
    from app.research.retriever import retrieve
    from app.services import dossier_service as svc

    spec = json.loads(file.read_text())["cases"] if file.exists() else []
    labelled = [c for c in spec if c.get("relevant_urls") or c.get("expect_insufficient") or c.get("expect_contradiction")]
    skipped = [c["query"] for c in spec if c not in labelled]
    if not labelled:
        return {"status": "no_labelled_cases", "skipped_unlabelled": len(skipped),
                "note": "Nothing was scored. Run --init, label the cases by hand, then rerun."}
    rows, dossier_rows, by_type = [], [], {}
    with SessionLocal() as db:
        for c in labelled:
            pq = process_query(c["query"], c["time_range"])
            window = max(parse_time_range(pq.time_range).total_seconds() / 86400, 1)
            cands = retrieve(db, pq.cleaned, svc.default_sources(), pq.time_range, keywords=pq.keywords, phrases=pq.phrases)
            ranked = rank(cands, pq.keywords, window, phrases=pq.phrases)
            chosen = select_evidence(ranked)
            urls = [r.candidate.document.url for r in chosen]
            if c.get("relevant_urls"):
                m = evaluate_query(urls, set(c["relevant_urls"]), k)
                m.update(diversity([publisher_of(r.candidate.document) for r in chosen]))
                m["duplicate_rate"] = duplicate_rate([r.candidate.document.canonical_url or r.candidate.document.url for r in chosen])
                rows.append(m)
                by_type.setdefault(c["type"], []).append(m)
            if with_dossiers:
                d, _ = svc.create_dossier(db, topic_id=c.get("topic_id"), query=None if c.get("topic_id") else c["query"], time_range=c["time_range"])
                if svc.claim_run(db, d.id):
                    svc.generate(d.id)
                db.expire_all()
                out = svc.serialize(db, svc.get_dossier(db, d.id))
                claims, _ = svc.list_claims(db, d.id, limit=200)
                dm = dossier_metrics(out, claims, set(c.get("expected_gaps") or []) or None)
                dm["type"] = c["type"]
                dm["insufficient_flagged"] = out["evidence_quality"]["dimensions"]["coverage"]["label"] == "insufficient"
                if c.get("expect_insufficient"):
                    dm["insufficient_expected"] = True
                dossier_rows.append(dm)
    report = {"status": "ok", "k": k, "scored_cases": len(labelled), "skipped_unlabelled": len(skipped),
              "retrieval": aggregate(rows) if rows else None,
              "retrieval_by_type": {t: aggregate(v) for t, v in by_type.items()}}
    if with_dossiers:
        report["dossiers"] = {key: mean_of(dossier_rows, key) for key in ("citation_coverage", "claim_support_rate", "unsupported_claim_rate", "completeness", "gap_recall", "gap_precision")}
        exp = [r for r in dossier_rows if r.get("insufficient_expected")]
        report["dossiers"]["insufficient_evidence_detected"] = f"{sum(1 for r in exp if r['insufficient_flagged'])}/{len(exp)}" if exp else None
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--dossiers", action="store_true")
    ap.add_argument("--file", type=Path, default=FILE)
    a = ap.parse_args()
    print(json.dumps(init_template() if a.init else run(a.k, a.dossiers, a.file), indent=2))
