"""
Semantic chunker with adaptive sizing per content type.
Preserves rich metadata on every chunk for attribution and downstream eval.
"""

import hashlib
import re
from typing import Iterator

import tiktoken

# Tokens per chunk by content type
_CHUNK_TOKENS: dict[str, int] = {
    "youtube_transcript": 600,
    "reddit_thread":      500,
    "glassdoor_review":   350,
    "article":            400,
    "forum_post":         400,
    "teamblind_post":     400,
}
_OVERLAP_TOKENS: dict[str, int] = {
    "youtube_transcript": 100,
    "reddit_thread":       80,
    "glassdoor_review":    40,
    "article":             60,
    "forum_post":          60,
    "teamblind_post":      60,
}
MIN_CHUNK_CHARS = 120
# Docs shorter than this are emitted as a single chunk without splitting
_NO_SPLIT_THRESHOLD = 500

_enc = tiktoken.get_encoding("cl100k_base")


def _token_len(text: str) -> int:
    return len(_enc.encode(text))


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    sentences = re.split(r"(?<=[.!?])\s+|\n\n+", text)
    return [s.strip() for s in sentences if s.strip()]


def _hard_split(text: str, max_tokens: int) -> list[str]:
    """Split a single oversized sentence by word boundaries."""
    words = text.split()
    parts: list[str] = []
    buf: list[str] = []
    buf_tok = 0
    for w in words:
        w_tok = _token_len(w)
        if buf_tok + w_tok > max_tokens and buf:
            parts.append(" ".join(buf))
            buf, buf_tok = [], 0
        buf.append(w)
        buf_tok += w_tok
    if buf:
        parts.append(" ".join(buf))
    return parts


def _chunk_sentences(
    sentences: list[str], chunk_tokens: int, overlap_tokens: int
) -> Iterator[str]:
    # Hard-split any sentence that already exceeds chunk_tokens
    expanded: list[str] = []
    for s in sentences:
        if _token_len(s) > chunk_tokens:
            expanded.extend(_hard_split(s, chunk_tokens))
        else:
            expanded.append(s)
    sentences = expanded

    current: list[str] = []
    current_tok = 0

    for sent in sentences:
        sent_tok = _token_len(sent)
        if current_tok + sent_tok > chunk_tokens and current:
            yield " ".join(current)
            # Build overlap from the tail of the current chunk
            overlap_buf: list[str] = []
            buf_tok = 0
            for s in reversed(current):
                t = _token_len(s)
                if buf_tok + t > overlap_tokens:
                    break
                overlap_buf.insert(0, s)
                buf_tok += t
            current = overlap_buf
            current_tok = buf_tok
        current.append(sent)
        current_tok += sent_tok

    if current:
        yield " ".join(current)


def chunk_document(doc: dict) -> list[dict]:
    content = doc.get("content", "")
    content_type = doc.get("content_type", doc.get("source_type", "unknown"))

    chunk_tokens = _CHUNK_TOKENS.get(content_type, 400)
    overlap_tokens = _OVERLAP_TOKENS.get(content_type, 80)

    # Short documents → single chunk, no splitting
    if len(content) < _NO_SPLIT_THRESHOLD:
        texts = [content.strip()] if content.strip() else []
    else:
        sentences = _split_sentences(content)
        texts = list(_chunk_sentences(sentences, chunk_tokens, overlap_tokens))

    texts = [t for t in texts if len(t) >= MIN_CHUNK_CHARS]
    total = len(texts)

    chunks = []
    for i, text in enumerate(texts):
        chunk_id = hashlib.md5(f"{doc.get('id', '')}-{i}".encode()).hexdigest()
        chunks.append({
            # ── Identity ──────────────────────────────────────────────
            "chunk_id":    chunk_id,
            "doc_id":      doc.get("id", ""),
            "chunk_index": i,
            "chunk_total": total,
            # ── Content ───────────────────────────────────────────────
            "text":        text,
            "char_count":  len(text),
            "token_count": _token_len(text),
            # ── Attribution (frontend + filtering) ────────────────────
            "source_type":  doc.get("source_type", "unknown"),
            "content_type": content_type,
            "source_name":  doc.get("source_name", doc.get("title", "")),
            "url":          doc.get("url", ""),
            "company":      doc.get("company", "Both"),
            "round_type":   doc.get("round_type", "General"),
            # ── Extended (eval + debugging) ───────────────────────────
            "title":          doc.get("title", doc.get("source_name", "")),
            "scraped_at":     doc.get("scraped_at", ""),
            "quality_score":  doc.get("_quality_score", 0.0),
            # ── Source-specific ───────────────────────────────────────
            "author":           doc.get("author", ""),
            "subreddit":        doc.get("subreddit", ""),
            "duration_seconds": doc.get("duration_seconds", 0),
            "video_path":       doc.get("video_path", ""),
            # Glassdoor review fields
            "review_index":      doc.get("review_index", -1),
            "review_date":       doc.get("review_date", ""),
            "review_location":   doc.get("review_location", ""),
            "review_outcome":    doc.get("review_outcome", ""),
            "review_difficulty": doc.get("review_difficulty", ""),
        })
    return chunks


def chunk_all(docs: list[dict]) -> list[dict]:
    all_chunks: list[dict] = []
    for doc in docs:
        all_chunks.extend(chunk_document(doc))
    return all_chunks
