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


def fit_topics(texts: list[str], embeddings: np.ndarray, min_topic_size: int | None = None) -> TopicModelResult:
    n = len(texts)
    if n < MIN_DOCS:
        raise ValueError(f"Need at least {MIN_DOCS} documents for topic modeling, got {n}")

    from bertopic import BERTopic
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    min_size = min_topic_size or max(5, n // 40)
    umap_model = UMAP(
        n_neighbors=min(15, n - 1),
        n_components=min(5, n - 2),
        min_dist=0.0,
        metric="cosine",
        random_state=RANDOM_STATE,
    )
    hdbscan_model = HDBSCAN(
        min_cluster_size=min_size,
        min_samples=max(2, min_size // 2),
        metric="euclidean",
        cluster_selection_method="eom",
        prediction_data=True,
    )
    vectorizer = CountVectorizer(stop_words="english", ngram_range=(1, 2), min_df=2 if n >= 50 else 1)
    model = BERTopic(
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer,
        calculate_probabilities=False,
        verbose=False,
    )
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
    )
