"""Text preparation for the trend pipeline."""
import re
from html import unescape

import numpy as np

_URL = re.compile(r"https?://\S+")
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

MIN_CHARS = 20


def clean_for_topics(text: str) -> str:
    text = unescape(_TAG.sub(" ", text or ""))
    text = _URL.sub(" ", text)
    text = re.sub(r"[^\w\s\-\+\.#']", " ", text)
    return _WS.sub(" ", text).strip()


_EN_STOP = frozenset(
    "the and of to in is for on with that this are as it by from at be or an was have has not but you they their "
    "will can more about new how what when who its into than also been were which".split()
)
_TOKEN = re.compile(r"[A-Za-z']+")
MIN_TOKENS_FOR_STOPWORD_CHECK = 12
MIN_STOPWORD_RATIO = 0.08


def is_probably_english(text: str, min_ascii_ratio: float = 0.9) -> bool:
    """Deterministic English guard (no external model).

    1. Mostly non-ASCII text (CJK, Cyrillic, Arabic...) is rejected.
    2. For texts with >= 12 words, the share of common English function words must be >= 8%; this
       rejects Latin-script languages (Spanish, French, German...) that pass the ASCII test.
    Short texts (titles) cannot be judged reliably and fall back to the ASCII test alone.
    This is a heuristic, not a language identifier; its error rate is measured in app/evaluation.
    """
    if not text:
        return False
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    if ascii_chars / len(text) < min_ascii_ratio:
        return False
    words = _TOKEN.findall(text.lower())
    if len(words) < MIN_TOKENS_FOR_STOPWORD_CHECK:
        return True
    return sum(1 for w in words if w in _EN_STOP) / len(words) >= MIN_STOPWORD_RATIO


REJECT_REASONS = (
    "empty_text", "too_short", "non_english", "duplicate_content",
    "invalid_embedding", "embedding_dimension_mismatch", "embedding_model_mismatch",
)
SAMPLE_LIMIT = 5


def validate_embedding(vec, expected_dim: int | None) -> str | None:
    """Return a rejection reason, or None when the vector is usable."""
    try:
        arr = np.asarray(vec, dtype=np.float32)
    except (TypeError, ValueError):
        return "invalid_embedding"
    if arr.ndim != 1 or arr.size == 0:
        return "invalid_embedding"
    if expected_dim is not None and arr.size != expected_dim:
        return "embedding_dimension_mismatch"
    if not np.all(np.isfinite(arr)) or float(np.linalg.norm(arr)) == 0.0:
        return "invalid_embedding"
    return None


def prepare(docs: list[dict], expected_dim: int | None = None, expected_model: str | None = None) -> tuple[list[dict], dict]:
    """docs: dicts with 'id' and 'text' (optionally 'vec' and 'embedding_model').

    Returns (kept, stats). Nothing is dropped silently: every rejection is counted by reason in `stats`
    (keys kept from the original contract: input/too_short/non_english/duplicate/kept) and up to
    SAMPLE_LIMIT document ids per reason are listed in stats['rejected_samples'].
    """
    kept, seen = [], set()
    stats: dict = {"input": len(docs), "too_short": 0, "non_english": 0, "duplicate": 0}
    reasons = {r: 0 for r in REJECT_REASONS}
    samples: dict[str, list[str]] = {}

    def reject(reason: str, doc_id) -> None:
        reasons[reason] += 1
        samples.setdefault(reason, [])
        if len(samples[reason]) < SAMPLE_LIMIT:
            samples[reason].append(str(doc_id))

    for d in docs:
        if expected_model is not None and d.get("embedding_model") not in (None, expected_model):
            reject("embedding_model_mismatch", d.get("id"))
            continue
        if "vec" in d:
            bad = validate_embedding(d["vec"], expected_dim)
            if bad:
                reject(bad, d.get("id"))
                continue
        raw = d.get("text")
        if not raw or not str(raw).strip():
            reject("empty_text", d.get("id"))
            continue
        t = clean_for_topics(raw)
        if len(t) < MIN_CHARS:
            stats["too_short"] += 1
            reject("too_short", d.get("id"))
            continue
        if not is_probably_english(t):
            stats["non_english"] += 1
            reject("non_english", d.get("id"))
            continue
        key = t.lower()
        if key in seen:
            stats["duplicate"] += 1
            reject("duplicate_content", d.get("id"))
            continue
        seen.add(key)
        kept.append({**d, "text": t})
    stats["kept"] = len(kept)
    stats["rejected"] = sum(reasons.values())
    stats["reasons"] = reasons
    stats["rejected_samples"] = samples
    return kept, stats
