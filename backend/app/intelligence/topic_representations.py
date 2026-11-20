"""Topic representations: readable names and centroid embeddings."""
import numpy as np


def topic_name(terms: list[str], max_terms: int = 3) -> str:
    picked = []
    for t in terms:
        if any(t in p or p in t for p in picked):  # skip overlapping uni/bi-grams
            continue
        picked.append(t)
        if len(picked) >= max_terms:
            break
    return " / ".join(p.title() for p in picked) if picked else "Unnamed Topic"


def centroid(vectors: np.ndarray) -> np.ndarray:
    c = np.asarray(vectors, dtype=np.float32).mean(axis=0)
    n = np.linalg.norm(c)
    return c / n if n else c


def nearest_topics(target: np.ndarray, others: dict[str, np.ndarray], k: int = 3) -> list[tuple[str, float]]:
    """Cosine-nearest topics, for 'related topics'."""
    if not others:
        return []
    keys = list(others)
    mat = np.vstack([others[key] for key in keys])
    mat = mat / np.clip(np.linalg.norm(mat, axis=1, keepdims=True), 1e-9, None)
    t = target / (np.linalg.norm(target) or 1.0)
    sims = mat @ t
    order = np.argsort(-sims)[:k]
    return [(keys[i], float(sims[i])) for i in order]


def match_topics(
    new: dict[int, np.ndarray], prior: dict[str, np.ndarray], threshold: float
) -> dict[int, tuple[str, float]]:
    """One-to-one continuity matching between newly fitted topics and stored topics.

    All (new, prior) pairs with cosine >= threshold are sorted by similarity and assigned greedily, so
    a stored topic is claimed by at most one new topic (the most similar), and the other candidates
    become new topics instead of silently sharing/stealing a history.
    """
    if not new or not prior:
        return {}
    nkeys, pkeys = list(new), list(prior)
    n = np.vstack([new[k] for k in nkeys]).astype(np.float32)
    p = np.vstack([prior[k] for k in pkeys]).astype(np.float32)
    n /= np.clip(np.linalg.norm(n, axis=1, keepdims=True), 1e-9, None)
    p /= np.clip(np.linalg.norm(p, axis=1, keepdims=True), 1e-9, None)
    sims = n @ p.T
    pairs = [(float(sims[i, j]), i, j) for i in range(len(nkeys)) for j in range(len(pkeys)) if sims[i, j] >= threshold]
    pairs.sort(reverse=True)
    out: dict[int, tuple[str, float]] = {}
    used: set[int] = set()
    for sim, i, j in pairs:
        if nkeys[i] in out or j in used:
            continue
        out[nkeys[i]] = (pkeys[j], sim)
        used.add(j)
    return out
