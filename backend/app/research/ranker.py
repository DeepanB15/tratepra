"""Research relevance score: R = 0.45 S + 0.25 K + 0.20 F + 0.10 Q (each 0-100).

This is independent of the Trend Score.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import get_settings


@dataclass
class RankedItem:
    candidate: object
    semantic: float
    keyword: float
    freshness: float
    quality: float
    score: float
    semantic_raw: float = 0.0  # cosine similarity x100 before pool normalisation


_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-\+#]*")

# Small, explicit synonym table (extend as needed). A keyword matches if it or a synonym is present.
SYNONYMS: dict[str, list[str]] = {
    "ai": ["artificial intelligence"],
    "llm": ["large language model", "language model"],
    "llms": ["large language models", "language models"],
    "agent": ["agentic", "autonomous"],
    "agents": ["agentic", "autonomous"],
    "coding": ["programming", "software development"],
    "trend": ["trending", "rising", "emerging"],
    "trends": ["trending", "rising", "emerging"],
}


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def keyword_relevance(text: str, keywords: list[str], phrases: list[str] | tuple[str, ...] = ()) -> float:
    """0-100. 80% token overlap (light stemming + synonyms) and 20% adjacent-phrase match.

    Phrase matching rewards texts that keep consecutive query words together, e.g. "ai agents".
    """
    if not keywords and not phrases:
        return 0.0
    tokens = _tokens(text)
    stems = {_stem(t) for t in tokens}
    low = " ".join(tokens)

    def hit(k: str) -> bool:
        return _stem(k) in stems or any(syn in low for syn in SYNONYMS.get(k, []))

    # Whole phrases ("claude code", quoted text) count as extra terms and must appear contiguously.
    phrase_hits = sum(1 for ph in phrases if ph in low)
    total_terms = len(keywords) + len(phrases)
    token_score = 100.0 * (sum(1 for k in keywords if hit(k)) + phrase_hits) / total_terms
    if len(keywords) < 2:
        return token_score
    stemmed_text = " ".join(_stem(t) for t in tokens)
    stemmed_kw = [_stem(k) for k in keywords]
    bigrams = [f"{a} {b}" for a, b in zip(stemmed_kw, stemmed_kw[1:])]
    phrase_score = 100.0 * sum(1 for g in bigrams if g in stemmed_text) / len(bigrams)
    return 0.8 * token_score + 0.2 * phrase_score


def freshness(published_at: datetime | None, window_days: float, now: datetime | None = None) -> float:
    """100 for just published, linearly decaying to 0 at the edge of the window.
    Unknown publication time gets a neutral 0 (not invented)."""
    if published_at is None:
        return 0.0
    now = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - published_at).total_seconds() / 86400.0)
    return max(0.0, 100.0 * (1.0 - age_days / max(window_days, 1e-6)))


def combine(semantic: float, keyword: float, fresh: float, quality: float, weights: dict | None = None) -> float:
    s = get_settings()
    w = weights or {
        "s": s.rank_w_semantic,
        "k": s.rank_w_keyword,
        "f": s.rank_w_freshness,
        "q": s.rank_w_quality,
    }
    return w["s"] * semantic + w["k"] * keyword + w["f"] * fresh + w["q"] * quality


def normalize_semantic(sims: list[float], min_candidates: int = 5, min_spread: float = 5.0) -> list[float]:
    """Rescale cosine-based scores to the candidate pool's spread (0-100).

    Raw cosine similarities from sentence encoders sit in a narrow band (often 20-60), which
    under-weights S against the keyword/freshness/quality components that already span 0-100.
    With too few candidates, or no spread, raw values are kept.
    """
    if len(sims) < min_candidates:
        return list(sims)
    lo, hi = min(sims), max(sims)
    if hi - lo < min_spread:
        return list(sims)
    return [100.0 * (v - lo) / (hi - lo) for v in sims]


def rank(
    candidates: list,
    keywords: list[str],
    window_days: float,
    now: datetime | None = None,
    phrases: list[str] | tuple[str, ...] = (),
    normalize: bool | None = None,
) -> list[RankedItem]:
    do_norm = get_settings().rank_normalize_semantic if normalize is None else normalize
    raw = [c.semantic for c in candidates]
    sem = normalize_semantic(raw) if do_norm else list(raw)
    items = []
    for c, s_norm, s_raw in zip(candidates, sem, raw):
        d = c.document
        k = keyword_relevance(d.normalized_text, keywords, phrases)
        f = freshness(d.published_at, window_days, now)
        items.append(
            RankedItem(
                candidate=c,
                semantic=s_norm,
                keyword=k,
                freshness=f,
                quality=c.quality,
                score=combine(s_norm, k, f, c.quality),
                semantic_raw=s_raw,
            )
        )
    items.sort(key=lambda i: i.score, reverse=True)
    return items
