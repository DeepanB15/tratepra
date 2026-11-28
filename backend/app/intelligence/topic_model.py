"""BERTopic pipeline: precomputed embeddings -> UMAP -> HDBSCAN -> c-TF-IDF representation.

Seeded for reproducibility. Noise documents (topic -1) are kept out of topics and
reported separately.
"""
from dataclasses import dataclass

import numpy as np

MIN_DOCS = 20
RANDOM_STATE = 42


@dataclass
class TopicModelResult:
    assignments: list[int]  # topic index per doc, -1 = noise
    probabilities: list[float | None]
    topic_terms: dict[int, list[str]]
    n_noise: int
    model: object
    notes: list[str] | None = None  # parameter fallbacks applied during this fit (surfaced in run diagnostics)


def model_parameters(n: int, min_topic_size: int | None = None) -> dict:
    """Every parameter that shapes the result. Part of the run key; derived from the document count."""
    min_size = min_topic_size or max(5, n // 40)
    return {
        "pipeline": "precomputed-embeddings -> UMAP -> HDBSCAN -> BERTopic c-TF-IDF",
        "random_state": RANDOM_STATE,
        "min_docs": MIN_DOCS,
        "umap": {"n_neighbors": min(15, n - 1), "n_components": min(5, n - 2), "min_dist": 0.0, "metric": "cosine"},
        "hdbscan": {"min_cluster_size": min_size, "min_samples": max(2, min_size // 2), "metric": "euclidean", "cluster_selection_method": "eom"},
        "vectorizer": {"stop_words": "english", "ngram_range": [1, 2], "min_df": 2 if n >= 50 else 1},
    }


def fit_topics(texts: list[str], embeddings: np.ndarray, min_topic_size: int | None = None) -> TopicModelResult:
    n = len(texts)
    if n < MIN_DOCS:
        raise ValueError(f"Need at least {MIN_DOCS} documents for topic modeling, got {n}")

    from bertopic import BERTopic
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    p = model_parameters(n, min_topic_size)
    notes: list[str] = []

    def build(min_df: int):
        umap_model = UMAP(random_state=RANDOM_STATE, **p["umap"])
        hdbscan_model = HDBSCAN(prediction_data=True, **p["hdbscan"])
        vz = p["vectorizer"]
        vectorizer = CountVectorizer(stop_words=vz["stop_words"], ngram_range=tuple(vz["ngram_range"]), min_df=min_df)
        return BERTopic(
            umap_model=umap_model, hdbscan_model=hdbscan_model, vectorizer_model=vectorizer,
            calculate_probabilities=False, verbose=False,
        )

    min_df = p["vectorizer"]["min_df"]
    try:
        model = build(min_df)
        topics, probs = model.fit_transform(texts, embeddings=embeddings)
    except ValueError as exc:
        # BERTopic fits the vectorizer on per-TOPIC documents, so min_df=2 can prune every term when topics
        # share no vocabulary. Retry once with min_df=1 and say so; any other error propagates.
        if "pruning" not in str(exc) or min_df <= 1:
            raise
        notes.append("vectorizer min_df lowered from 2 to 1: every term was pruned (topics share no vocabulary)")
        model = build(1)
        topics, probs = model.fit_transform(texts, embeddings=embeddings)

    terms: dict[int, list[str]] = {}
    for t in set(topics):
        if t == -1:
            continue
        terms[t] = [w for w, _ in (model.get_topic(t) or [])[:10]]

    if probs is None:
        probabilities = [None] * n
    else:
        probabilities = [float(p) if np.ndim(p) == 0 else float(np.max(p)) for p in probs]
    return TopicModelResult(
        assignments=[int(t) for t in topics],
        probabilities=probabilities,
        topic_terms=terms,
        n_noise=int(sum(1 for t in topics if t == -1)),
        model=model,
        notes=notes or None,
    )
