"""Collect data for one or more queries across configured sources.

Usage: python -m scripts.collect_data "AI coding agents" "LLM agents" --sources google_news youtube --range 30d
"""
import argparse
import json

from app.core.database import SessionLocal, init_db
from app.core.logging import setup_logging
from app.ingestion.collector import collect
from app.services.source_service import ensure_sources


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser()
    p.add_argument("queries", nargs="+")
    p.add_argument("--sources", nargs="*", default=None)
    p.add_argument("--range", default="30d")
    args = p.parse_args()

    init_db()
    ensure_sources()
    with SessionLocal() as db:
        for q in args.queries:
            print(f"== {q}")
            print(json.dumps(collect(db, q, args.sources, args.range), indent=2, default=str))


if __name__ == "__main__":
    main()
