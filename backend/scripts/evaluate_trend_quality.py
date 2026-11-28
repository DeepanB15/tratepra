"""Measure topic-discovery quality on the CURRENT database without writing anything (dry run).

Usage:  python -m scripts.evaluate_trend_quality [--out docs/phase-1/TREND_QUALITY_REPORT.generated.md]

Writes a markdown report of MEASURED values (eligible documents, rejections, topics, noise, size distribution,
embedding cohesion, name coverage, score coverage, flags) and a manual-review table with empty verdict columns.
Nothing is judged automatically as "good": semantic coherence needs a human reviewer filling the table in.
"""
import argparse
import sys
from pathlib import Path

from app.core.database import SessionLocal
from app.core.logging import setup_logging
from app.services import trend_service


def render(r: dict) -> str:
    L: list[str] = ["# Trend quality evaluation (generated, dry run — nothing was persisted)", ""]
    L.append(f"- Status: **{r['status']}**  ·  run key: `{r.get('run_key', '')[:16]}…`")
    inp, prep = r.get("input", {}), r.get("prep", {})
    L += ["", "## Input", "", "| Measure | Value |", "|---|---|"]
    for k in ("text_documents_in_window", "with_embedding", "without_embedding", "non_text_documents_in_window", "undated_text_documents", "future_dated"):
        L.append(f"| {k.replace('_', ' ')} | {inp.get(k, '—')} |")
    L.append(f"| eligible after validation | {prep.get('kept', '—')} |")
    L.append(f"| rejected | {prep.get('rejected', '—')} |")
    for reason, n in (prep.get("reasons") or {}).items():
        if n:
            L.append(f"| &nbsp;&nbsp;rejected: {reason.replace('_', ' ')} | {n} |")
    tq = r.get("topic_quality")
    if not tq:
        return "\n".join(L + ["", f"No topic model output (status `{r['status']}`)."])
    ts = tq["topic_size"]
    L += ["", "## Topic model", "", "| Measure | Value |", "|---|---|",
          f"| topics discovered | {tq['topics_discovered']} |", f"| documents in topics | {tq['documents_in_topics']} |",
          f"| noise documents | {tq['noise_documents']} ({tq['noise_percentage']}%) |",
          f"| topic size min / mean / median / max | {ts['min']} / {ts['mean']} / {ts['median']} / {ts['max']} |",
          f"| size histogram | {ts['histogram']} |", f"| source distribution | {tq['source_distribution']} |",
          f"| embedding cohesion mean / min | {tq['cohesion']['mean']} / {tq['cohesion']['min']} (tightness only, not semantic coherence) |"]
    for f in tq.get("run_flags", []):
        L.append(f"\n> ⚠ {f}")
    for f in tq.get("topic_flags", []):
        L.append(f"\n> ⚠ topic #{f['topic_index']}: {f['flag']} — {f['detail']}")
    topics = r.get("topic_details", [])
    withheld = sum(1 for t in topics if t["score_withheld"])
    L += ["", "## Scores and naming", "",
          f"- Topics with a withheld score: **{withheld} / {len(topics)}**",
          f"- Topics flagged for naming review: **{sum(1 for t in topics if t['needs_review'])} / {len(topics)}**",
          f"- Identity outcomes vs stored topics: {r.get('identity', {}).get('outcomes')}", "",
          "## Manual review (fill in; do not publish metrics from unreviewed rows)", "",
          "| # | Name | Size | Name coverage | Score / coverage | Top terms | Representative titles | Coherent? (y/n) | Too broad? | Duplicate of # | Name OK? | Explanation accurate? |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, t in enumerate(sorted(topics, key=lambda x: -x["size"]), 1):
        score = "withheld" if t["score_withheld"] else f"{t['score']:.0f}"
        titles = "<br>".join(x.replace("|", "/")[:80] for x in t["representative_titles"])
        L.append(f"| {i} | {t['name']} | {t['size']} | {t['name_coverage']} | {score} / {t['score_coverage']} | {', '.join(t['terms'][:5])} | {titles} |  |  |  |  |  |")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/phase-1/TREND_QUALITY_REPORT.generated.md")
    args = ap.parse_args()
    setup_logging()
    with SessionLocal() as db:
        result = trend_service.recompute(db, dry_run=True)
    md = render(result)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"status={result['status']} topics={result.get('topics')} -> {args.out}")
    return 0 if result["status"] == "dry_run" else 2


if __name__ == "__main__":
    sys.exit(main())
