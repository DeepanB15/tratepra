
"""Optional article enrichment for Google News RSS records."""

import logging

from app.ingestion.article_fetcher import fetch_article

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
            enriched.append(updated)
            continue

        url = updated.get("url")

        if not url:
            metadata["article_extraction"] = {
                "status": "unavailable",
                "method": "trafilatura",
            }
            enriched.append(updated)
            continue

        attempted += 1

        try:
            result = fetch_article(url)

            if result and result.status == "extracted" and result.text:
                rss_text = updated.get("description") or ""
                updated["description"] = rss_text or None

                updated["metadata"]["article_extraction"] = {
                    "status": "extracted",
                    "method": result.method,
                    "characters": len(result.text),
                }

                updated["_article_text"] = result.text

            else:
                metadata["article_extraction"] = {
                    "status": "unavailable",
                    "method": "trafilatura",
                }

        except Exception:
            log.exception("Article enrichment failed")
            metadata["article_extraction"] = {
                "status": "error",
                "method": "trafilatura",
            }

        enriched.append(updated)

    return enriched
