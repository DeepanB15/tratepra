import hashlib
import re
from html import unescape
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref"}


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return _WS.sub(" ", unescape(_TAG.sub(" ", text))).strip()


def canonical_url(url: str | None) -> str | None:
    if not url:
        return None
    p = urlparse(url.strip())
    if not p.scheme or not p.netloc:
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING])
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), host, path, "", query, ""))


def content_hash(title: str, description: str | None) -> str:
    base = f"{title.lower().strip()}|{(description or '').lower().strip()[:500]}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def normalize_record(rec: dict) -> dict:
    """Connector record -> document dict. Never invents timestamps or engagement."""
    title = clean_text(rec.get("title"))
    description = clean_text(rec.get("description")) or None
    text = f"{title}. {description}" if description else title
    return {
        "source": rec["source"],
        "external_id": str(rec["external_id"])[:512],
        "title": title,
        "description": description,
        "normalized_text": text,
        "url": rec.get("url"),
        "canonical_url": canonical_url(rec.get("url")),
        "content_hash": content_hash(title, description),
        "published_at": rec.get("published_at"),
        "collected_at": rec.get("collected_at"),
        "engagement": rec.get("engagement") or {},
        "metadata": rec.get("metadata") or {},
    }


def validation_error(doc: dict) -> str | None:
    """Reason a normalized document must be rejected, or None when it is acceptable.

    Only structural problems reject a record. Missing dates/engagement/URLs stay None.
    """
    if not doc.get("source"):
        return "missing source"
    if not str(doc.get("external_id") or "").strip():
        return "missing external_id"
    if not (doc.get("title") or "").strip():
        return "missing title"
    return None
