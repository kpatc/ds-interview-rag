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
    "qa_technical":       350,  # one question + context prefix per chunk
}
_OVERLAP_TOKENS: dict[str, int] = {
    "youtube_transcript": 100,
    "reddit_thread":       80,
    "glassdoor_review":    40,
    "article":             60,
    "forum_post":          60,
    "teamblind_post":      60,
    "qa_technical":         0,  # no overlap — each question is self-contained
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


_QA_SPLIT_RE = re.compile(r"\n+(?=q\d+\s*:)", re.IGNORECASE)

# Rough topic detection for Q&A questions
_QA_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "SQL":              ["sql", "select", "join", "query", "table", "window function"],
    "statistics":       ["precision", "recall", "p-value", "hypothesis", "distribution", "variance", "bias"],
    "machine learning": ["regression", "classification", "gradient", "overfitting", "cross-validation", "feature"],
    "probability":      ["probability", "bayes", "conditional", "random variable"],
    "Python":           ["python", "pandas", "numpy", "list comprehension", "dictionary"],
}

def _detect_qa_topic(question_text: str) -> str:
    t = question_text.lower()
    for topic, kws in _QA_TOPIC_KEYWORDS.items():
        if any(kw in t for kw in kws):
            return topic
    return "Data Science"


def _split_qa_document(doc: dict) -> list[str]:
    """Split Q&A content per question, adding a retrieval-friendly context prefix."""
    company = doc.get("company", "Both")
    round_type = doc.get("round_type", "Technical")
    source_name = doc.get("source_name", "")

    # Extract source label (e.g. "DataLemur" from "DataLemur — BCG Technical Interview Questions")
    source_label = source_name.split("—")[0].strip() if "—" in source_name else source_name[:20]

    raw = doc.get("content", "")
    questions = [q.strip() for q in _QA_SPLIT_RE.split(raw) if q.strip()]

    chunks = []
    for q in questions:
        topic = _detect_qa_topic(q)
        prefix = f"[{company} {round_type} Interview Question | {topic} | {source_label}]"
        chunks.append(f"{prefix}\n\n{q}")
    return chunks


def _detect_oa_platform(doc: dict) -> tuple[str, str]:
    """
    Returns (company_label, platform) for an image_ocr doc.
    BCG uses CodeSignal; McKinsey uses HackerRank.
    Falls back to content scan if company field is ambiguous.
    """
    company = doc.get("company", "Both").strip()
    content = (doc.get("content", "") + " " + doc.get("question_summary", "")).lower()

    if company == "BCG":
        return "BCG", "CodeSignal"
    if company in ("McKinsey", "MBB"):
        return "McKinsey", "HackerRank"

    # Ambiguous — scan extracted text for platform signals
    if "codesignal" in content or "code signal" in content:
        return "BCG", "CodeSignal"
    if "hackerrank" in content or "hacker rank" in content:
        return "McKinsey", "HackerRank"

    # Default: treat as BCG CodeSignal (most screenshots in dataset are BCG)
    return "BCG", "CodeSignal"


def _image_ocr_prefix(doc: dict) -> str:
    """Build a searchable context prefix for OA screenshot chunks."""
    company, platform = _detect_oa_platform(doc)
    parts = [f"[{company} OA {platform} Exercise"]
    qt = doc.get("question_type", "")
    if qt:
        parts.append(f"| {qt}")
    topics = doc.get("topics", [])
    if topics:
        parts.append(f"| Topics: {', '.join(topics)}")
    diff = doc.get("difficulty", "")
    if diff:
        parts.append(f"| Difficulty: {diff}")
    parts.append("]")
    return " ".join(parts)


def chunk_document(doc: dict) -> list[dict]:
    content = doc.get("content", "")
    content_type = doc.get("content_type", doc.get("source_type", "unknown"))

    # Q&A technical questions: split per question with topic prefix
    if content_type == "qa_technical" and content.strip():
        texts = [t for t in _split_qa_document(doc) if len(t) >= MIN_CHUNK_CHARS]
        total = len(texts)
        chunks = []
        for i, text in enumerate(texts):
            chunk_id = hashlib.md5(f"{doc.get('id', '')}-{i}".encode()).hexdigest()
            chunks.append({
                "chunk_id": chunk_id, "doc_id": doc.get("id", ""),
                "chunk_index": i, "chunk_total": total,
                "text": text, "char_count": len(text), "token_count": _token_len(text),
                "source_type": doc.get("source_type", "article"),
                "content_type": content_type,
                "source_name": doc.get("source_name", ""),
                "url": doc.get("url", ""), "company": doc.get("company", "Both"),
                "round_type": doc.get("round_type", "Technical"),
                "title": doc.get("source_name", ""), "scraped_at": doc.get("scraped_at", ""),
                "quality_score": doc.get("_quality_score", 0.0),
                "author": "", "subreddit": "", "duration_seconds": 0, "video_path": "",
                "review_index": -1, "review_date": "", "review_location": "",
                "review_outcome": "", "review_difficulty": "",
                "question_type": "", "topics": [], "question_summary": "",
                "difficulty": "", "screen_count": 1,
            })
        return chunks

    # Prepend searchable context header for OA screenshots so BM25 can find them
    if content_type == "image_ocr" and content.strip():
        content = _image_ocr_prefix(doc) + "\n\n" + content

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
            # OA screenshot fields (image_ocr)
            "question_type":     doc.get("question_type", ""),
            "topics":            doc.get("topics", []),
            "question_summary":  doc.get("question_summary", ""),
            "difficulty":        doc.get("difficulty", ""),
            "screen_count":      doc.get("screen_count", 1),
        })
    return chunks


def chunk_all(docs: list[dict]) -> list[dict]:
    all_chunks: list[dict] = []
    for doc in docs:
        all_chunks.extend(chunk_document(doc))
    return all_chunks
