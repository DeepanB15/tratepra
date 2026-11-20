"""Text preparation for the trend pipeline."""
import re
from html import unescape

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


def prepare(docs: list[dict]) -> tuple[list[dict], dict]:
    """docs: dicts with at least 'id' and 'text'. Returns (kept, stats)."""
    kept, seen = [], set()
    stats = {"input": len(docs), "too_short": 0, "non_english": 0, "duplicate": 0}
    for d in docs:
        t = clean_for_topics(d["text"])
        if len(t) < MIN_CHARS:
            stats["too_short"] += 1
            continue
        if not is_probably_english(t):
            stats["non_english"] += 1
            continue
        key = t.lower()
        if key in seen:
            stats["duplicate"] += 1
            continue
        seen.add(key)
        kept.append({**d, "text": t})
    stats["kept"] = len(kept)
    return kept, stats
