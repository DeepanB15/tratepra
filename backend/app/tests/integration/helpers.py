"""Seed helpers for Phase 1 integration tests."""
from datetime import datetime, timedelta, timezone

import numpy as np

from app.core.config import get_settings
from app.intelligence.topic_model import TopicModelResult
from app.models import Document, DocumentEmbedding, Source
from sqlalchemy import select

from .conftest import fake_embed

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
CLUSTERS = {
    "kubernetes": ["kubernetes", "operators", "scaling"],
    "rust": ["rust", "compiler", "borrow"],
    "solar": ["solar", "battery", "storage"],
}
_counter = {"n": 0}


def add_docs(db, cluster: str, n: int, source: str = "google_news", days_old: float = 3.0, model: str | None = None):
    """Add n distinct English text docs about `cluster`, each with a stored (fake) embedding."""
    src = db.scalar(select(Source).where(Source.key == source))
    settings = get_settings()
    out = []
    for _ in range(n):
        _counter["n"] += 1
        i = _counter["n"]
        text = f"{' '.join(CLUSTERS[cluster])} teams report update number {i} in production"
        d = Document(
            source_id=src.id, external_id=f"{cluster}-{i}", title=f"{cluster.title()} story {i}", url=f"https://example.com/{cluster}/{i}",
            normalized_text=text, content_hash=f"hash-{i}", published_at=NOW - timedelta(days=days_old, minutes=i), collected_at=NOW, engagement={},
        )
        db.add(d)
        db.flush()
        db.add(DocumentEmbedding(document_id=d.id, embedding=fake_embed([text])[0].tolist(), model=model or settings.embedding_model, text_hash=f"th-{i}"))
        out.append(d)
    db.commit()
    return out


def keyword_fit(drop: tuple[str, ...] = ()):
    """Deterministic stand-in for BERTopic: topic = cluster keyword found in the text. Clusters in `drop` become noise."""
    names = list(CLUSTERS)

    def fit(texts, embeddings, min_topic_size=None):
        assign, terms = [], {}
        for t in texts:
            idx = next((j for j, c in enumerate(names) if c in t and c not in drop), -1)
            assign.append(idx)
        for j, c in enumerate(names):
            if j in assign:
                terms[j] = [f"{c} {CLUSTERS[c][1]}", c, CLUSTERS[c][1]]
        return TopicModelResult(assign, [0.9 if a != -1 else None for a in assign], terms, assign.count(-1), None)

    return fit


def seed_three_clusters(db, n_each: int = 10):
    for c in CLUSTERS:
        add_docs(db, c, n_each)
