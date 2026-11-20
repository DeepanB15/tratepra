"""Run topic discovery + trend scoring and append a new observation per topic.

Usage: python -m scripts.run_trend_analysis
Schedule this periodically (e.g. daily); each run is a new historical snapshot.
"""
import json

from app.core.database import SessionLocal, init_db
from app.core.logging import setup_logging
from app.ingestion.embedding_store import embed_pending
from app.services import trend_service


def main() -> None:
    setup_logging()
    init_db()
    with SessionLocal() as db:
        embed_pending(db)
        print(json.dumps(trend_service.recompute(db), indent=2, default=str))


if __name__ == "__main__":
    main()
