
"""Optional article enrichment for Google News RSS records."""

import logging

from app.ingestion.article_fetcher import fetch_article_outcome
from app.ingestion.article_state import build_state

log = logging.getLogger(__name__)

MAX_ARTICLES_PER_RUN = 5


def enrich_records(records: list[dict]) -> list[dict]:
    """Enrich a bounded number of records without discarding RSS content."""
    enriched = []

    attempted = 0

    for record in records:
        updated = dict(record)
        metadata = dict(updated.get("metadata") or {})

        updated["metadata"] = metadata

        if updated.get("source") != "google_news":
            enriched.append(updated)
            continue

        if attempted >= MAX_ARTICLES_PER_RUN:
            metadata["article_extraction"] = {
                "status": "skipped_limit",
                "method": "trafilatura",
            }
            updated["_article"] = build_state(None, "not_attempted_limit")
            enriched.append(updated)
            continue

        url = updated.get("url")

        if not url:
            metadata["article_extraction"] = {
                "status": "unavailable",
                "method": "trafilatura",
            }
            updated["_article"] = build_state(None, "no_url")
            enriched.append(updated)
            continue

        attempted += 1

        try:
            outcome = fetch_article_outcome(url)
            result = outcome.result

            if result and result.status == "extracted" and result.text:
                rss_text = updated.get("description") or ""
                updated["description"] = rss_text or None

                updated["metadata"]["article_extraction"] = {
                    "status": "extracted",
                    "method": result.method,
                    "characters": len(result.text),
                }

                updated["_article_text"] = result.text
                updated["_article"] = build_state(result.text, None, result.method)

            else:
                metadata["article_extraction"] = {
                    "status": "unavailable",
                    "method": "trafilatura",
                }
                updated["_article"] = build_state(None, outcome.reason)

        except Exception:
            log.exception("Article enrichment failed")
            metadata["article_extraction"] = {
                "status": "error",
                "method": "trafilatura",
            }
            updated["_article"] = build_state(None, "error")

        enriched.append(updated)

    return enriched
