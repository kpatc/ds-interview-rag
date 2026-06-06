"""
FAISS vector store + BM25 index, persisted to disk.
Supports metadata filtering (company, round_type) before search.
"""

import json
import logging
import pickle
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from .embedder import embed_passages

log = logging.getLogger(__name__)

INDEX_DIR = Path(__file__).parent.parent.parent / "data" / "embeddings"

FAISS_FILE = INDEX_DIR / "faiss.index"
BM25_FILE = INDEX_DIR / "bm25.pkl"
CHUNKS_FILE = INDEX_DIR / "chunks.json"


def build_index(chunks: list[dict]) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    texts = [c["text"] for c in chunks]

    # ── FAISS (dense) ──
    log.info(f"Embedding {len(texts)} chunks...")
    vecs = embed_passages(texts)
    dim = vecs.shape[1]
    index = faiss.IndexFlatIP(dim)  # cosine after L2-norm
    index.add(vecs)
    faiss.write_index(index, str(FAISS_FILE))
    log.info(f"FAISS index saved ({index.ntotal} vectors, dim={dim})")

    # ── BM25 (sparse) ──
    tokenized = [t.lower().split() for t in texts]
    bm25 = BM25Okapi(tokenized)
    with open(BM25_FILE, "wb") as f:
        pickle.dump(bm25, f)
    log.info("BM25 index saved")

    # ── Chunk metadata ──
    CHUNKS_FILE.write_text(json.dumps(chunks, ensure_ascii=False, indent=2))
    log.info(f"Chunks metadata saved ({len(chunks)} chunks)")


def load_index() -> tuple[faiss.Index, BM25Okapi, list[dict]]:
    if not FAISS_FILE.exists():
        raise FileNotFoundError("Index not found — run build_index.py first")
    index = faiss.read_index(str(FAISS_FILE))
    with open(BM25_FILE, "rb") as f:
        bm25 = pickle.load(f)
    chunks = json.loads(CHUNKS_FILE.read_text())
    return index, bm25, chunks


def search_dense(
    query_vec: np.ndarray,
    index: faiss.Index,
    chunks: list[dict],
    top_k: int = 20,
    company_filter: Optional[str] = None,
    round_filter: Optional[str] = None,
) -> list[tuple[int, float]]:
    scores, indices = index.search(query_vec, min(top_k * 4, index.ntotal))
    results = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < 0:
            continue
        chunk = chunks[idx]
        if company_filter and company_filter != "Both":
            if chunk["company"] not in (company_filter, "Both"):
                continue
        if round_filter and round_filter != "All":
            if chunk["round_type"] != round_filter:
                continue
        results.append((int(idx), float(score)))
        if len(results) >= top_k:
            break
    return results


def search_bm25(
    query: str,
    bm25: BM25Okapi,
    chunks: list[dict],
    top_k: int = 20,
    company_filter: Optional[str] = None,
    round_filter: Optional[str] = None,
) -> list[tuple[int, float]]:
    tokens = query.lower().split()
    scores = bm25.get_scores(tokens)
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    results = []
    for idx, score in ranked:
        if score <= 0:
            break
        chunk = chunks[idx]
        if company_filter and company_filter != "Both":
            if chunk["company"] not in (company_filter, "Both"):
                continue
        if round_filter and round_filter != "All":
            if chunk["round_type"] != round_filter:
                continue
        results.append((int(idx), float(score)))
        if len(results) >= top_k:
            break
    return results
