"""Activity aggregation over consistent windows and search-interest signal."""
from datetime import datetime, timedelta, timezone

import numpy as np

from app.intelligence.growth import normalize_growth


def window_edges(end: datetime, window_days: int, n_windows: int) -> list[tuple[datetime, datetime]]:
    """Consecutive windows, oldest first, last window ends at `end`."""
    edges = []
    for i in range(n_windows):
        w_end = end - timedelta(days=window_days * (n_windows - 1 - i))
        edges.append((w_end - timedelta(days=window_days), w_end))
    return edges


def window_counts(timestamps: list[datetime | None], edges: list[tuple[datetime, datetime]]) -> list[int]:
    counts = [0] * len(edges)
    for ts in timestamps:
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        for i, (a, b) in enumerate(edges):
            if a < ts <= b:
                counts[i] += 1
                break
    return counts


def search_interest_signal(points: list[tuple[datetime, float]]) -> float | None:
    """0-100 normalised change in search interest: mean of last third vs first third.
    Needs at least 6 points; returns None otherwise (not zero)."""
    if len(points) < 6:
        return None
    pts = sorted(points, key=lambda p: p[0])
    vals = np.array([v for _, v in pts], dtype=float)
    k = max(2, len(vals) // 3)
    first, last = vals[:k].mean(), vals[-k:].mean()
    if first <= 0:
        return None if last <= 0 else 100.0
    pct = (last - first) / first * 100.0
    return normalize_growth(pct)


def terms_overlap(query: str, topic_terms: list[str]) -> bool:
    q = {t for t in query.lower().split() if len(t) > 2}
    tt = {w for term in topic_terms for w in term.lower().split()}
    return bool(q & tt)
