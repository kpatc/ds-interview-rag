"""
Advanced hybrid retriever:
  1. Multi-query expansion — generate 3 query variants via Claude
  2. HyDE — embed a hypothetical answer for denser retrieval signal
  3. BM25 + dense search on all query variants
  4. RRF (Reciprocal Rank Fusion) to merge ranked lists
  5. Cross-encoder reranking of top candidates
"""

import logging
import os
from typing import Optional

import numpy as np
from groq import Groq
from sentence_transformers import CrossEncoder

from .embedder import embed_query
from .vectorstore import load_index, search_bm25, search_dense

log = logging.getLogger(__name__)

_groq_client: Optional[Groq] = None
_cross_encoder: Optional[CrossEncoder] = None
_index_data = None  # (faiss_index, bm25, chunks)

CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"
UTILITY_MODEL = "llama-3.1-8b-instant"  # fast model for query expansion + HyDE
RRF_K = 60


def _get_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


def _get_cross_encoder() -> CrossEncoder:
    global _cross_encoder
    if _cross_encoder is None:
        log.info(f"Loading cross-encoder: {CROSS_ENCODER_MODEL}")
        _cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL)
    return _cross_encoder


def _get_index():
    global _index_data
    if _index_data is None:
        _index_data = load_index()
    return _index_data


def _expand_queries(query: str, n: int = 3) -> list[str]:
    """Generate query variants for multi-query retrieval."""
    try:
        resp = _get_client().chat.completions.create(
            model=UTILITY_MODEL,
            max_tokens=256,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a search query optimizer for a RAG system about "
                        "BCG X and McKinsey QuantumBlack data science interviews. "
                        "Generate alternative phrasings that capture the same intent."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Generate {n} alternative search queries for: '{query}'\n"
                        "Return ONLY the queries, one per line, no numbering."
                    ),
                },
            ],
        )
        lines = resp.choices[0].message.content.strip().split("\n")
        variants = [l.strip() for l in lines if l.strip()][:n]
        return [query] + variants
    except Exception as e:
        log.warning(f"Query expansion failed: {e}")
        return [query]


def _hyde(query: str) -> str:
    """Generate a hypothetical answer passage to improve dense retrieval."""
    try:
        resp = _get_client().chat.completions.create(
            model=UTILITY_MODEL,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Write a short (3-4 sentence) factual answer to this interview question "
                        f"about BCG X or McKinsey QuantumBlack data science roles:\n\n{query}"
                    ),
                }
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        log.warning(f"HyDE failed: {e}")
        return query


def _rrf_merge(ranked_lists: list[list[tuple[int, float]]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion across multiple ranked lists."""
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, (idx, _) in enumerate(ranked):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def retrieve(
    query: str,
    top_k: int = 6,
    company_filter: Optional[str] = None,
    round_filter: Optional[str] = None,
    use_hyde: bool = True,
    use_multi_query: bool = True,
) -> list[dict]:
    faiss_idx, bm25, chunks = _get_index()

    # ── 1. Query variants ──
    queries = _expand_queries(query) if use_multi_query else [query]
    log.info(f"Using {len(queries)} query variants")

    # ── 2. HyDE: hypothetical document embedding ──
    hyde_text = _hyde(query) if use_hyde else query

    all_ranked: list[list[tuple[int, float]]] = []

    for q in queries:
        qvec = embed_query(q)
        dense_res = search_dense(qvec, faiss_idx, chunks, top_k=20,
                                  company_filter=company_filter, round_filter=round_filter)
        bm25_res = search_bm25(q, bm25, chunks, top_k=20,
                                company_filter=company_filter, round_filter=round_filter)
        all_ranked.extend([dense_res, bm25_res])

    # HyDE dense search
    hyde_vec = embed_query(hyde_text)
    hyde_res = search_dense(hyde_vec, faiss_idx, chunks, top_k=20,
                             company_filter=company_filter, round_filter=round_filter)
    all_ranked.append(hyde_res)

    # ── 3. RRF fusion ──
    fused = _rrf_merge(all_ranked)
    candidate_indices = [idx for idx, _ in fused[:40]]

    # ── 4. Cross-encoder reranking ──
    ce = _get_cross_encoder()
    pairs = [(query, chunks[i]["text"]) for i in candidate_indices]
    ce_scores = ce.predict(pairs)
    reranked = sorted(zip(candidate_indices, ce_scores), key=lambda x: x[1], reverse=True)

    # ── 5. Deduplicate by doc_id (max 1 chunk per source document) ──
    seen_docs: set[str] = set()
    results = []
    for idx, score in reranked:
        chunk = chunks[idx].copy()
        chunk["_score"] = float(score)
        doc_id = chunk.get("doc_id", chunk["chunk_id"])
        if doc_id in seen_docs:
            continue
        seen_docs.add(doc_id)
        results.append(chunk)
        if len(results) >= top_k:
            break

    log.info(f"Retrieved {len(results)} chunks after reranking")
    return results
