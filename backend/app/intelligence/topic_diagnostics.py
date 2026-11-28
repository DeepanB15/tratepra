"""Run-level topic-model diagnostics (pure). Everything here is measured from the run's own output.

`cohesion` is the mean cosine similarity of member embeddings to the topic centroid. It is an embedding-space
tightness measure, NOT a semantic-coherence score; no coherence claim is made without human review.
"""
from collections import Counter
from statistics import mean, median

import numpy as np


def _dist(sizes: list[int]) -> dict:
    if not sizes:
        return {"min": None, "max": None, "mean": None, "median": None, "histogram": {}}
    bins = Counter()
    for s in sizes:
        label = "<10" if s < 10 else "10-19" if s < 20 else "20-49" if s < 50 else "50-99" if s < 100 else "100+"
        bins[label] += 1
    return {"min": min(sizes), "max": max(sizes), "mean": round(mean(sizes), 2), "median": median(sizes), "histogram": dict(bins)}


def topic_cohesion(vectors: np.ndarray, centroid: np.ndarray) -> float:
    v = np.asarray(vectors, dtype=np.float32)
    v = v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-9, None)
    c = np.asarray(centroid, dtype=np.float32)
    c = c / (np.linalg.norm(c) or 1.0)
    return float(np.mean(v @ c))


def run_diagnostics(
    assignments: list[int],
    sources: list[str],
    topic_terms: dict[int, list[str]],
    cohesion: dict[int, float],
    languages: dict[str, int] | None = None,
    broad_share: float = 0.40,
    high_noise_share: float = 0.60,
) -> dict:
    n = len(assignments)
    topic_ids = sorted({t for t in assignments if t != -1})
    sizes = {t: sum(1 for a in assignments if a == t) for t in topic_ids}
    clustered = sum(sizes.values())
    noise = n - clustered
    noise_share = (noise / n) if n else 0.0

    per_source: dict[str, dict[str, int]] = {}
    for a, s in zip(assignments, sources):
        d = per_source.setdefault(s, {"documents": 0, "in_topics": 0, "noise": 0})
        d["documents"] += 1
        d["noise" if a == -1 else "in_topics"] += 1

    flags: list[dict] = []
    for t in topic_ids:
        share = sizes[t] / clustered if clustered else 0.0
        if share > broad_share:
            flags.append({"topic_index": t, "flag": "overly_broad", "detail": f"holds {round(100 * share)}% of clustered documents"})
        if not topic_terms.get(t):
            flags.append({"topic_index": t, "flag": "no_representation", "detail": "no c-TF-IDF terms extracted"})
    run_flags: list[str] = []
    if noise_share > high_noise_share:
        run_flags.append(f"high_noise: {round(100 * noise_share)}% of documents were not assigned to any topic")
    if len(topic_ids) == 1 and n >= 40:
        run_flags.append("single_topic: all clustered documents fell into one topic")

    return {
        "eligible_documents": n,
        "documents_in_topics": clustered,
        "noise_documents": noise,
        "noise_percentage": round(100 * noise_share, 2),
        "topics_discovered": len(topic_ids),
        "topic_size": _dist(list(sizes.values())),
        "topic_sizes": {str(t): sizes[t] for t in topic_ids},
        "source_distribution": dict(Counter(sources)),
        "per_source": per_source,
        "language_distribution": languages or {},
        "cohesion": {
            "metric": "mean cosine of member embeddings to topic centroid (embedding tightness, not semantic coherence)",
            "mean": round(mean(cohesion.values()), 4) if cohesion else None,
            "min": round(min(cohesion.values()), 4) if cohesion else None,
        },
        "topic_flags": flags,
        "run_flags": run_flags,
    }
