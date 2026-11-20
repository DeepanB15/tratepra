"""Novelty: how semantically distinct a topic is from previously observed topics.

High novelty is relative distinctiveness in the observed dataset, not proof that the
topic never existed.
"""
import numpy as np


def novelty_score(topic_vec: np.ndarray, historical_vecs: list[np.ndarray] | np.ndarray) -> float | None:
    """0-100. Returns None when there is no history to compare against (not 0, not 100)."""
    hist = np.asarray(historical_vecs, dtype=np.float32)
    if hist.size == 0:
        return None
    v = np.asarray(topic_vec, dtype=np.float32)
    v = v / (np.linalg.norm(v) or 1.0)
    norms = np.linalg.norm(hist, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    sims = (hist / norms) @ v
    nearest = float(np.max(sims))
    # Sentence-embedding cosine rarely goes below ~0 for topics; clamp and invert.
    return max(0.0, min(100.0, (1.0 - max(0.0, nearest)) * 100.0))
