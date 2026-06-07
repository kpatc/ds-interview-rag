"""
Load and normalize all raw JSON files into a flat list of documents.
Handles both single-dict records and nested {results: [...]} Reddit format.
Integrates per-source cleaning (cleaner.py) and Glassdoor splitting (splitter.py).
"""

import json
import logging
from pathlib import Path
from typing import Iterator

from .cleaner import clean
from .splitter import split_glassdoor

log = logging.getLogger(__name__)

RAW_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

MIN_CONTENT_CHARS = 300  # default — filters noise and scraping failures
# Some source types have short but valid content
_MIN_CHARS_BY_SOURCE: dict[str, int] = {
    "image_ocr":    50,   # OA screenshot questions split across screens
    "qa_technical": 80,   # individual Q&A interview questions
}


def _quality_score(doc: dict) -> float:
    """
    0–1 score estimating retrieval value of a document.
    Used downstream for ranking and eval filtering.
    """
    length = len(doc.get("content", ""))
    source_weight = {
        "glassdoor": 0.30, "article": 0.28, "youtube": 0.25,
        "reddit": 0.20, "teamblind": 0.18, "forum": 0.15,
    }.get(doc.get("source_type", ""), 0.10)

    url = doc.get("url", "")
    round_bonus = 0.10 if doc.get("round_type", "General") not in ("General", "All") else 0.05

    score = (
        min(length / 8000, 0.50)
        + source_weight
        + (0.10 if url.startswith("http") else 0.0)
        + round_bonus
    )
    return round(min(score, 1.0), 3)


def _iter_file(path: Path) -> Iterator[dict]:
    try:
        data = json.loads(path.read_text())
    except Exception as e:
        log.warning(f"Cannot parse {path.name}: {e}")
        return

    if isinstance(data, dict) and "results" in data:
        records = data["results"]
    elif isinstance(data, dict):
        records = [data]
    elif isinstance(data, list):
        records = data
    else:
        return

    for rec in records:
        if not isinstance(rec, dict):
            continue

        rec = dict(rec)
        rec["company"] = rec.get("company", "Both").strip()
        rec["round_type"] = rec.get("round_type", "General").strip()
        rec["source_type"] = rec.get("source_type", "unknown")
        rec.setdefault("_file", str(path.relative_to(RAW_DIR)))

        # Clean content + derive content_type
        rec = clean(rec)

        # Glassdoor: one file → many individual reviews
        if rec["source_type"] == "glassdoor":
            n_ok = 0
            for review in split_glassdoor(rec):
                if len(review.get("content", "")) >= MIN_CONTENT_CHARS:
                    review["_quality_score"] = _quality_score(review)
                    n_ok += 1
                    yield review
            log.debug(f"  glassdoor {path.name}: {n_ok} reviews extracted")
            continue

        # Check by content_type first (more specific), then source_type
        ct_key = rec.get("content_type", rec.get("source_type", ""))
        st_key = rec.get("source_type", "")
        min_chars = _MIN_CHARS_BY_SOURCE.get(ct_key) or _MIN_CHARS_BY_SOURCE.get(st_key) or MIN_CONTENT_CHARS
        if len(rec.get("content", "")) < min_chars:
            continue

        rec["_quality_score"] = _quality_score(rec)
        yield rec


def load_all_documents(raw_dir: Path = RAW_DIR) -> list[dict]:
    docs = []
    source_counts: dict[str, int] = {}
    for path in sorted(raw_dir.rglob("*.json")):
        if path.name == "manifest.json":
            continue
        # Skip the raw source files that were already extracted to .extracted.json
        # (the .extracted.json itself is loaded instead)
        if path.name.endswith(".extracted.json"):
            pass  # load normally — it IS the extracted doc
        elif any(path.parent.glob(path.name + ".extracted.json")):
            continue  # skip: image/pdf already has its extracted JSON
        for doc in _iter_file(path):
            docs.append(doc)
            st = doc.get("source_type", "unknown")
            source_counts[st] = source_counts.get(st, 0) + 1

    log.info(f"Loaded {len(docs)} documents — {source_counts}")
    return docs
