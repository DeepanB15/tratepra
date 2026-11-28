"""Deterministic run identity for the trend pipeline (pure functions).

Two executions that analyse the same documents with the same configuration over the same analysis
window must produce the same key, so the second can be recognised and short-circuited.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone


def analysis_anchor(now: datetime) -> datetime:
    """End of the analysis window: the start of the NEXT UTC day.

    Anchoring to a day boundary (instead of the wall clock) makes same-day re-runs over identical data
    identical, while a run on a later day sees a genuinely different temporal state and gets its own key.
    The final window therefore covers (anchor - window_days, anchor] and includes documents from today.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)


def document_fingerprint(docs: list[tuple[str, ...]]) -> str:
    """docs: (document_id, content_hash, embedding_text_hash, published_at_iso, ...). Order-independent."""
    h = hashlib.sha256()
    for row in sorted(docs):
        h.update(("|".join(row) + "\n").encode())
    return h.hexdigest()


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_run_key(*, documents_fingerprint: str, window_end: datetime, configuration: dict) -> str:
    """configuration must contain every parameter that can change the result: topic-model parameters,
    window sizes, embedding model + dimension, matching thresholds, trend weights and formula version."""
    payload = {
        "documents": documents_fingerprint,
        "window_end": window_end.astimezone(timezone.utc).isoformat(),
        "configuration": configuration,
    }
    return hashlib.sha256(_canonical(payload).encode()).hexdigest()
