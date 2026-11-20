from threading import Lock

import numpy as np

from app.core.config import get_settings

_model = None
_lock = Lock()


def get_model():
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(get_settings().embedding_model)
        return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """L2-normalised embeddings, so cosine similarity == dot product."""
    if not texts:
        return np.zeros((0, get_settings().embedding_dim), dtype=np.float32)
    vecs = get_model().encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
    return np.asarray(vecs, dtype=np.float32)


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text])[0]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def model_name() -> str:
    return get_settings().embedding_model
