"""Article evidence states.

A document is evidence at one of these levels. RSS-only is never presented as a full article.

  full         extracted article text, complete (not cut at the extraction cap) and >= PARTIAL_BELOW chars
  partial      extracted article text that is short (< PARTIAL_BELOW chars) or was truncated at the cap
  rss_only     only the connector's title/description exist; no article extraction was attempted
  unavailable  extraction was attempted/possible but produced no usable text (no URL, paywall, empty page)
  too_short    text was extracted but below the minimum useful length
  failed       the fetch itself failed (blocked URL, HTTP error, timeout, not HTML, too large, ...)
"""
import hashlib
from datetime import datetime, timezone

from app.ingestion.article_extractor import MAX_ARTICLE_CHARS

FULL, PARTIAL, RSS_ONLY = "full", "partial", "rss_only"
UNAVAILABLE, FAILED, TOO_SHORT = "unavailable", "failed", "too_short"
STATES = (FULL, PARTIAL, RSS_ONLY, UNAVAILABLE, FAILED, TOO_SHORT)
HAS_ARTICLE_TEXT = (FULL, PARTIAL)

PARTIAL_BELOW = 800  # chars; configurable here, documented in docs/phase-2

_FETCH_FAILURES = {
    "blocked_unsafe_url", "blocked_unsafe_redirect", "too_many_redirects", "redirect_without_location",
    "not_html", "response_too_large", "timeout", "network_error", "error",
}


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify(extracted_text: str | None, reason: str | None) -> str:
    """Map an extraction outcome to a state. `reason` is the fetcher/extractor reason when no text exists."""
    if extracted_text:
        n = len(extracted_text)
        return PARTIAL if (n < PARTIAL_BELOW or n >= MAX_ARTICLE_CHARS) else FULL
    if reason == "insufficient_content":
        return TOO_SHORT
    if reason and (reason.startswith("http_") or reason in _FETCH_FAILURES):
        return FAILED
    if reason in ("not_attempted_limit", "not_attempted_source"):
        return RSS_ONLY
    return UNAVAILABLE


def build_state(extracted_text: str | None, reason: str | None, method: str = "trafilatura") -> dict:
    """Column values for a document's article evidence."""
    return {
        "article_status": classify(extracted_text, reason),
        "article_method": method,
        "article_failure_reason": None if extracted_text else (reason or "no_text"),
        "article_extracted_at": datetime.now(timezone.utc) if extracted_text else None,
        "article_text": extracted_text or None,
        "article_text_hash": text_hash(extracted_text) if extracted_text else None,
    }


def compose_normalized_text(base: str, article_text: str | None) -> str:
    """Single source of truth for what is indexed and embedded: RSS text, then article text."""
    return f"{base}\n\n{article_text}" if article_text else base
