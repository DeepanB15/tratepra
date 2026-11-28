"""Run topic discovery + trend scoring as a tracked, idempotent TrendRun.

Usage:
  python -m scripts.run_trend_analysis              # run (or recognise an identical completed run)
  python -m scripts.run_trend_analysis --dry-run    # full analysis, writes NOTHING (safe on a live database)
  python -m scripts.run_trend_analysis --skip-embed # do not embed pending documents first

Repeating the command over unchanged data on the same UTC day returns status "unchanged" and appends nothing.
Exit code: 0 ok/unchanged/dry_run, 1 failed, 2 not enough data for topic modeling.
"""
import argparse
import json
import sys

from app.core.database import SessionLocal, init_db
from app.core.logging import setup_logging
from app.ingestion.embedding_store import embed_pending
from app.services import trend_service


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="analyse and print diagnostics without persisting anything")
    ap.add_argument("--skip-embed", action="store_true")
    args = ap.parse_args()
    setup_logging()
    if not args.dry_run:
        init_db()
    with SessionLocal() as db:
        if not (args.dry_run or args.skip_embed):
            embed_pending(db)
        try:
            result = trend_service.recompute(db, dry_run=args.dry_run)
        except Exception as exc:
            print(json.dumps({"status": "failed", "error": trend_service.sanitize_error(exc)}, indent=2))
            return 1
        print(json.dumps(result, indent=2, default=str))
    return 2 if result.get("status") in ("insufficient_documents", "no_documents", "no_topics_found") else 0


if __name__ == "__main__":
    sys.exit(main())
