"""Engagement signal from source metadata (views/likes/comments/score).

Raw engagement is not comparable across platforms, so each document gets a
log-scaled platform-specific value and topics are percentile-ranked against each
other. Sources without engagement data (e.g. news RSS) contribute nothing; if a topic
has no engagement-bearing documents the signal is None (not zero).
"""
import math

import numpy as np


def doc_engagement(source_key: str, engagement: dict) -> float | None:
    e = engagement or {}
    if source_key == "youtube":
        views, likes, comments = e.get("viewCount"), e.get("likeCount"), e.get("commentCount")
        if views is None and likes is None and comments is None:
            return None
        return math.log1p(views or 0) + 2 * math.log1p(likes or 0) + 3 * math.log1p(comments or 0)
    if source_key == "reddit":
        score, comments = e.get("score"), e.get("num_comments")
        if score is None and comments is None:
            return None
        return math.log1p(max(score or 0, 0)) + 2 * math.log1p(comments or 0)
    return None


def topic_engagement_raw(doc_values: list[float | None]) -> float | None:
    vals = [v for v in doc_values if v is not None]
    if not vals:
        return None
    return float(np.mean(vals))


def percentile_normalize(raw_by_topic: dict[str, float | None]) -> dict[str, float | None]:
    """Percentile rank (0-100) among topics that have engagement data."""
    present = {k: v for k, v in raw_by_topic.items() if v is not None}
    out: dict[str, float | None] = {k: None for k in raw_by_topic}
    if not present:
        return out
    values = sorted(present.values())
    n = len(values)
    for k, v in present.items():
        if n == 1:
            out[k] = 50.0  # single data point: neutral, no ranking information
        else:
            rank = sum(1 for x in values if x < v) + 0.5 * (sum(1 for x in values if x == v) - 1)
            out[k] = 100.0 * rank / (n - 1)
    return out
