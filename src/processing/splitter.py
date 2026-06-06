"""
Split monolithic scraped documents into finer-grained sub-documents.

Currently handles Glassdoor exports: one file with 50-100 reviews
concatenated → individual review documents, each with its own metadata.
"""

import hashlib
import re

GLASSDOOR_SEP = "─────"  # U+2500 box-drawing dash × 5, injected by scraper

_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"


def split_glassdoor(doc: dict) -> list[dict]:
    """
    Split a monolithic Glassdoor export into individual interview reviews.
    Returns one doc dict per review, preserving parent metadata.
    """
    content = doc.get("content", "")
    parts = re.split(r"\n" + re.escape(GLASSDOOR_SEP) + r"\n", content)

    reviews = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue

        # Skip file-header block if it has no interview content
        if i == 0 and not re.search(r"(?:Application|Interview)\n", part):
            continue

        meta = _parse_header(part)
        clean_text = _strip_footer(part)

        if len(clean_text) < 80:
            continue

        review_id = hashlib.md5(
            f"{doc.get('id', '')}-review-{i}".encode()
        ).hexdigest()[:16]

        reviews.append({
            "id": review_id,
            "source_type": "glassdoor",
            "content_type": "glassdoor_review",
            "content": clean_text,
            "char_count": len(clean_text),
            "company": doc.get("company", "Both"),
            "round_type": doc.get("round_type", "General"),
            "url": doc.get("url", ""),
            "source_name": f"Glassdoor — {doc.get('company', '')} DS Interview",
            "scraped_at": doc.get("scraped_at", ""),
            "review_index": i,
            # Parsed from review header
            "review_date": meta.get("date", ""),
            "review_location": meta.get("location", ""),
            "review_outcome": meta.get("outcome", ""),
            "review_difficulty": meta.get("difficulty", ""),
            "review_experience": meta.get("experience", ""),
        })

    return reviews


def _parse_header(text: str) -> dict:
    """Extract structured fields from the first lines of a Glassdoor review."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    meta: dict[str, str] = {}

    for j, line in enumerate(lines[:10]):
        if re.match(rf"^{_MONTHS}\s+\d+", line):
            meta["date"] = line
        elif re.match(r"^(Accepted|No|Declined) offer", line, re.IGNORECASE):
            meta["outcome"] = line
        elif re.match(r"^(Positive|Negative|Neutral) experience", line, re.IGNORECASE):
            meta["experience"] = line
        elif re.match(r"^(Easy|Average|Difficult) interview", line, re.IGNORECASE):
            meta["difficulty"] = line
        elif "Anonymous Interview Candidate" in line or "Interview Candidate" in line:
            if j + 1 < len(lines):
                next_line = lines[j + 1]
                # Exclude lines that are clearly not a location
                if not re.match(
                    r"^(Accepted|No|Declined) offer|^(Positive|Negative|Neutral)|^(Easy|Average|Difficult)",
                    next_line, re.IGNORECASE,
                ):
                    meta["location"] = next_line

    return meta


def _strip_footer(text: str) -> str:
    """Remove boilerplate footer that Glassdoor appends to every review."""
    text = re.sub(r"\nread more\b.*", "", text)
    text = re.sub(r"\nAnswer question.*", "", text, flags=re.DOTALL)
    text = re.sub(r"\nHelpful\s*\nShare\s*\n?\d*", "", text)
    text = re.sub(r"Interview questions \[\d+\]\n?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
