"""
Embedding model wrapper — BGE-small-en-v1.5 (strong retrieval, runs on CPU).
Normalizes vectors so FAISS inner-product == cosine similarity.
"""

import logging
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-large-en-v1.5"  # upgraded from bge-small (768 vs 384 dims, +15 MTEB pts)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    log.info(f"Loading embedding model: {MODEL_NAME}")
    return SentenceTransformer(MODEL_NAME)


def embed_passages(texts: list[str], batch_size: int = 64) -> np.ndarray:
    model = _get_model()
    vecs = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 100,
        normalize_embeddings=True,
    )
    return np.array(vecs, dtype=np.float32)


def embed_query(query: str) -> np.ndarray:
    model = _get_model()
    vec = model.encode(
        QUERY_PREFIX + query,
        normalize_embeddings=True,
    )
    return np.array(vec, dtype=np.float32).reshape(1, -1)
