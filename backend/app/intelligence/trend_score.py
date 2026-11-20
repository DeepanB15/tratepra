"""Trend Score T = 0.30G + 0.20M + 0.15E + 0.15N + 0.10S + 0.10C (all 0-100).

Missing signals are never treated as zero. The score is computed over available
signals with weights renormalised, and withheld entirely if available weight falls
below the minimum coverage threshold.
"""
from dataclasses import dataclass

from app.core.config import Settings, get_settings

SIGNAL_NAMES = ["growth", "momentum", "engagement", "novelty", "search_interest", "cross_source_activity"]


def weights(s: Settings | None = None) -> dict[str, float]:
    s = s or get_settings()
    return {
        "growth": s.trend_w_growth,
        "momentum": s.trend_w_momentum,
        "engagement": s.trend_w_engagement,
        "novelty": s.trend_w_novelty,
        "search_interest": s.trend_w_search,
        "cross_source_activity": s.trend_w_cross_source,
    }


@dataclass
class ScoreResult:
    score: float | None
    coverage_weight: float  # fraction of total weight with data (0-1)
    available: list[str]
    missing: list[str]
    withheld: bool


def trend_score(signals: dict[str, float | None], w: dict[str, float] | None = None, min_coverage: float | None = None) -> ScoreResult:
    w = w or weights()
    min_cov = get_settings().trend_min_coverage if min_coverage is None else min_coverage
    total = sum(w.values())
    available = [k for k in SIGNAL_NAMES if signals.get(k) is not None]
    missing = [k for k in SIGNAL_NAMES if signals.get(k) is None]
    avail_weight = sum(w[k] for k in available)
    coverage = avail_weight / total if total else 0.0
    if not available or coverage < min_cov:
        return ScoreResult(None, coverage, available, missing, withheld=True)
    score = sum(w[k] * float(signals[k]) for k in available) / avail_weight
    return ScoreResult(round(score, 2), coverage, available, missing, withheld=False)
