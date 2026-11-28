"""Bounded, query-relevant excerpts - the single text that is shown to the LLM AND used to verify citations.

Showing the model one text and verifying against another would let claims pass (or fail) for the wrong
reason, so context_builder and the dossier engine both go through `build_excerpt`.
"""
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from app.ingestion.article_state import HAS_ARTICLE_TEXT

MAX_EXCERPT_CHARS = 700
RSS_SNIPPET_CHARS = 500
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_WORD = re.compile(r"[a-z0-9][a-z0-9\-\+#]*")


@dataclass
class Excerpt:
    text: str
    basis: str  # "article" (extracted article sentences) | "rss" (connector description)
    article_status: str


def _stem(t: str) -> str:
    return t[:-1] if t.endswith("s") and len(t) > 3 else t


def article_source_text(doc) -> str | None:
    """Article text for a document, or None when it is RSS-only / failed / unavailable / too short."""
    if (getattr(doc, "article_status", "rss_only") or "rss_only") not in HAS_ARTICLE_TEXT:
        return None
    # Legacy rows (pre-Phase-2) keep the article only inside normalized_text.
    return doc.article_text or doc.normalized_text or None


def build_excerpt(doc, terms: list[str] | None = None, max_chars: int = MAX_EXCERPT_CHARS) -> Excerpt:
    status = getattr(doc, "article_status", "rss_only") or "rss_only"
    article = article_source_text(doc)
    if not article:
        return Excerpt((doc.description or "")[:RSS_SNIPPET_CHARS], "rss", status)

    sentences = [s.strip() for s in _SENT.split(article) if len(s.strip()) > 20]
    if not sentences:
        return Excerpt((doc.description or "")[:RSS_SNIPPET_CHARS], "rss", status)
    wanted = {_stem(t.lower()) for t in (terms or []) if len(t) > 2}

    def score(sentence: str) -> int:
        return len(wanted & {_stem(w) for w in _WORD.findall(sentence.lower())})

    scored = sorted(range(len(sentences)), key=lambda i: (-score(sentences[i]), i))
    chosen, used = [], 0
    for i in scored:
        if wanted and score(sentences[i]) == 0 and chosen:
            break  # nothing else is query-relevant; do not pad with unrelated text
        if used + len(sentences[i]) > max_chars and chosen:
            continue
        chosen.append(i)
        used += len(sentences[i]) + 1
        if used >= max_chars:
            break
    text = " ".join(sentences[i] for i in sorted(chosen))[:max_chars]
    return Excerpt(text, "article", status)


def publisher_of(doc) -> str:
    """Best-effort publisher: connector metadata, else the URL host. Never invented."""
    meta = getattr(doc, "metadata_", None) or {}
    for key in ("publisher", "source_name", "channel", "subreddit"):
        if meta.get(key):
            return str(meta[key])
    host = urlparse(doc.canonical_url or doc.url or "").netloc.removeprefix("www.")
    if host:
        return host
    try:
        return doc.source.key
    except Exception:  # detached instance without the relationship loaded
        return "unknown"
