"""Evaluate change detection on synthetic controlled cases. Usage: python scripts/evaluate_change_detection.py [--file path] [--json]"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.evaluation.change_detection import evaluate  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--file", default=os.path.join(os.path.dirname(__file__), "..", "..", "data", "evaluation", "change_cases.json"))
ap.add_argument("--json", action="store_true")
ap.add_argument("--replay", action="store_true", help="read-only historical replay over the configured database (counts only)")
a = ap.parse_args()
if a.replay:
    from app.core.database import SessionLocal
    from app.evaluation.change_detection import replay_history

    with SessionLocal() as db:
        print(json.dumps(replay_history(db), indent=1))
    sys.exit(0)
rep = evaluate(json.load(open(a.file))["cases"])
if a.json:
    print(json.dumps(rep, indent=1))
else:
    print(f"[{rep['label']}] {rep['passed']}/{rep['cases']} cases passed; precision={rep['event_precision']} recall={rep['event_recall']}")
    for r in rep["results"]:
        print(("PASS " if r["passed"] else "FAIL ") + f"{r['id']:<48} expected={r['expected']} got={r['got']}" + ("" if r["passed"] else f" suppressed={r['suppressed']}"))
sys.exit(0 if rep["passed"] == rep["cases"] else 1)
