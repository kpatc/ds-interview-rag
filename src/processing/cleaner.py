"""
Per-source content cleaning.

Strips scraper-injected headers, formatting artifacts, and boilerplate
so chunks contain only meaningful text. Called before chunking.
"""

import html
import re


def clean(doc: dict) -> dict:
    """Return a copy of doc with cleaned content + content_type field."""
    doc = dict(doc)
    source_type = doc.get("source_type", "unknown")
    content = html.unescape(doc.get("content", ""))

    if source_type == "reddit":
        content, content_type = _clean_reddit(content)
    elif source_type == "youtube":
        content, content_type = _clean_youtube(content)
    elif source_type == "glassdoor":
        content, content_type = _clean_glassdoor_header(content)
    elif source_type == "teamblind":
        content, content_type = _clean_teamblind(content)
    else:  # article, forum
        content, content_type = content.strip(), source_type

    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    doc["content"] = content
    doc["content_type"] = content_type
    doc["char_count"] = len(content)
    return doc


# ── per-source cleaners ───────────────────────────────────────────────

def _clean_reddit(content: str) -> tuple[str, str]:
    # Strip the metadata header injected by the scraper
    content = re.sub(
        r"^TITLE:.*?\n(?:SUBREDDIT:.*?\n)?(?:AUTHOR:.*?\n)?(?:DATE:.*?\n)?(?:URL:.*?\n)?\n?",
        "",
        content,
        flags=re.MULTILINE,
    )
    # Replace visual dividers with clean section breaks
    content = re.sub(r"──+\s*ORIGINAL POST\s*──+\n?", "", content)
    content = re.sub(r"──+\s*COMMENT[AIRES]*\s*──+\n?", "\n\n---\n\n", content)
    return content.strip(), "reddit_thread"


def _clean_youtube(content: str) -> tuple[str, str]:
    # Strip header block (SOURCE/TITLE/CHANNEL/URL/DURATION/VIEWS/DATE/VIDEO_FILE)
    content = re.sub(
        r"^SOURCE:\s*YouTube\s*\nTITLE:.*?\nCHANNEL:.*?\nURL:.*?\n"
        r"(?:DURATION:.*?\n)?(?:VIEWS?:.*?\n)?(?:DATE:.*?\n)?(?:VIDEO_FILE:.*?\n)?\n?",
        "",
        content,
        flags=re.MULTILINE,
    )
    # Prefer transcript over description — extract transcript section if present
    transcript_m = re.search(
        r"──+\s*TRANSCRIPT\s*\(Whisper\)\s*──+\s*\n(.*)",
        content,
        re.DOTALL,
    )
    if transcript_m:
        content = transcript_m.group(1).strip()
    else:
        content = re.sub(r"──+\s*DESCRIPTION\s*──+\n?", "", content)
        content = re.sub(r"──+\s*TRANSCRIPT[^\n]*──+\n?", "", content)
    return content.strip(), "youtube_transcript"


def _clean_glassdoor_header(content: str) -> tuple[str, str]:
    # Strip the file-level header (SOURCE / COMPANY / ROLE / PAGES)
    content = re.sub(
        r"^SOURCE:\s*Glassdoor\s*\nCOMPANY:.*?\nROLE:.*?\nPAGES:.*?\n\n?",
        "",
        content,
        flags=re.MULTILINE,
    )
    return content.strip(), "glassdoor"


def _clean_teamblind(content: str) -> tuple[str, str]:
    return content.strip(), "teamblind_post"
