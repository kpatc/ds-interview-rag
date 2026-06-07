"""
Multimodal extractor: images (Gemini 2.0 Flash vision), PDFs, .txt, .csv.

Groups WhatsApp screenshots taken at the same second (same question, split
across multiple screens) and merges them into one rich document with structured
metadata: question_type, topics, question_summary, difficulty.

Saves extracted content as .extracted.json next to the base source file.
Run once (or re-run to force-refresh all images):
    python -m src.processing.multimodal
    python -m src.processing.multimodal --force
"""

import hashlib
import json
import logging
import os
import re
import time
from collections import defaultdict
from pathlib import Path

log = logging.getLogger(__name__)

RAW_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

IMAGE_EXTS = {".jpeg", ".jpg", ".png", ".webp"}
CSV_EXTS = {".csv"}
GEMINI_MODEL = "models/gemini-2.5-flash"
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
RATE_LIMIT_DELAY = 13.0  # Gemini free tier: 5 RPM
RATE_LIMIT_DELAY_GROQ = 3.0
MAX_RETRIES = 3

_IMAGE_PROMPT = """\
This is a screenshot from a BCG X or McKinsey QuantumBlack data science online \
assessment (CodeSignal or similar platform).

Extract and return a JSON object with EXACTLY these fields:

{
  "content": "<ALL visible text: problem title, full description, input/output specs, \
constraints, code, tables, formulas, answer options, every UI label>",
  "question_type": "<quiz_mcq | coding_problem | data_manipulation | ui_noise | other>",
  "topics": ["<precise DS/ML topic>", ...],
  "question_summary": "<1 sentence: what skill or concept this question tests>",
  "difficulty": "<easy | medium | hard>"
}

Definitions:
- quiz_mcq: multiple-choice question with numbered/lettered options
- coding_problem: write a function, SQL query, or algorithm from scratch
- data_manipulation: pandas/numpy data cleaning, transformation, or feature engineering task
- ui_noise: phone notifications, browser chrome, no actual assessment content
- topics: use precise terms e.g. "logistic regression", "gradient descent", \
"logloss", "SQL joins", "feature engineering", "time series", "cross-entropy"
- If the image shows ONLY answer options (no question visible), extract all option \
text and infer topics from the options

Return ONLY the raw JSON object — no markdown fences, no commentary."""


def _get_gemini_client():
    from google import genai
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _extract_image_gemini(path: Path) -> dict:
    """Extract structured metadata via Gemini 2.5 Flash. Raises on daily quota exhaustion."""
    from google.genai import types

    client = _get_gemini_client()
    image_bytes = path.read_bytes()
    ext = path.suffix.lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime), _IMAGE_PROMPT],
            )
            break
        except Exception as e:
            msg = str(e)
            # Daily quota exhausted — no point retrying
            if "GenerateRequestsPerDayPerProjectPerModel" in msg:
                raise
            retry_match = re.search(r"retry.*?(\d+(?:\.\d+)?)s", msg, re.IGNORECASE)
            wait = float(retry_match.group(1)) + 2 if retry_match else 30 * (attempt + 1)
            if attempt < MAX_RETRIES - 1 and ("429" in msg or "503" in msg):
                log.warning(f"    Rate limited, waiting {wait:.0f}s (attempt {attempt+1}/{MAX_RETRIES})")
                time.sleep(wait)
            else:
                raise
    else:
        raise RuntimeError(f"All {MAX_RETRIES} attempts failed")

    raw = resp.text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"content": raw, "question_type": "other", "topics": [], "question_summary": "", "difficulty": ""}


def _extract_image_groq(path: Path) -> dict:
    """Fallback: extract structured metadata via Groq Llama 4 Scout vision."""
    import base64
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    b64 = base64.standard_b64encode(path.read_bytes()).decode()
    ext = path.suffix.lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"

    resp = client.chat.completions.create(
        model=GROQ_VISION_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": _IMAGE_PROMPT},
        ]}],
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"content": raw, "question_type": "other", "topics": [], "question_summary": "", "difficulty": ""}


def _extract_image(path: Path) -> tuple[dict, str]:
    """Try Gemini first; fall back to Groq on daily quota exhaustion. Returns (result, backend)."""
    try:
        result = _extract_image_gemini(path)
        time.sleep(RATE_LIMIT_DELAY)
        return result, "gemini"
    except Exception as e:
        if "GenerateRequestsPerDayPerProjectPerModel" in str(e):
            log.warning(f"    Gemini daily quota exhausted — switching to Groq fallback")
            result = _extract_image_groq(path)
            time.sleep(RATE_LIMIT_DELAY_GROQ)
            return result, "groq"
        raise


def _timestamp_group_key(stem: str) -> str:
    """'WhatsApp Image 2026-01-20 at 18.38.16 (2)' → 'WhatsApp Image 2026-01-20 at 18.38.16'"""
    return re.sub(r"\s*\(\d+\)\s*$", "", stem).strip()


def _group_images_by_timestamp(paths: list[Path]) -> dict[str, list[Path]]:
    """Group images by base timestamp; base image (no variant) sorted first."""
    groups: dict[str, list[Path]] = defaultdict(list)
    for p in paths:
        groups[_timestamp_group_key(p.stem)].append(p)
    for key in groups:
        groups[key].sort(key=lambda p: (bool(re.search(r"\(\d+\)$", p.stem)), p.stem))
    return dict(groups)


# ── Non-image extractors ──────────────────────────────────────────────

def _extract_pdf(path: Path) -> str:
    import pdfplumber
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
    return "\n\n".join(pages)


# Filename → clean source name override for manually pasted files
_KNOWN_SOURCE_NAMES: dict[str, str] = {
    "dataInterview_content":        "DataInterview — BCG X Data Scientist Interview Guide",
    "datalemur_interview_question":  "DataLemur — BCG Technical Interview Questions",
    "datalemur_interview_questions": "DataLemur — McKinsey Technical Interview Questions",
}

_QA_RE = re.compile(r"^q\d+\s*:", re.IGNORECASE | re.MULTILINE)


def _is_qa_format(content: str) -> bool:
    return bool(_QA_RE.match(content.strip()))


def _extract_txt(path: Path) -> tuple[str, str]:
    """Returns (content, content_type)."""
    raw = path.read_text(errors="replace").strip()
    if _is_qa_format(raw):
        return raw, "qa_technical"
    return raw, "article"


def _extract_csv(path: Path) -> str:
    import csv
    from io import StringIO
    text = path.read_text(errors="replace")
    reader = csv.DictReader(StringIO(text))
    rows = list(reader)
    if not rows:
        return ""
    columns = list(rows[0].keys())
    lines = [
        f"Dataset: {path.stem}",
        f"Rows: {len(rows)} | Columns: {len(columns)}",
        "",
        "Columns: " + ", ".join(columns),
        "",
        "Sample rows (first 3):",
    ]
    for r in rows[:3]:
        lines.append("  " + " | ".join(f"{k}={v}" for k, v in list(r.items())[:10]))
    return "\n".join(lines)


# ── Metadata helpers ──────────────────────────────────────────────────

_COMPANY_MAP = {"bcg": "BCG", "mckinsey": "McKinsey", "both": "Both"}
_ROUND_MAP = {
    "oa": "OA", "general": "General", "technical": "Technical",
    "livecoding": "LiveCoding", "case": "Case", "pei": "PEI", "takehome": "TakeHome",
}


def _infer_metadata(path: Path, raw_dir: Path) -> tuple[str, str]:
    parts = [p.lower() for p in path.relative_to(raw_dir).parts]
    company = next((v for k, v in _COMPANY_MAP.items() if k in parts), "Both")
    round_type = next((v for k, v in _ROUND_MAP.items() if k in parts), "General")
    return company, round_type


def _make_source_name(company: str, question_type: str, topics: list[str], summary: str) -> str:
    type_label = {"quiz_mcq": "Quiz", "coding_problem": "Coding", "data_manipulation": "Data Task"}.get(question_type, "OA")
    if summary:
        label = summary[:70]
    elif topics:
        label = ", ".join(topics[:3])
    else:
        label = "Assessment Question"
    return f"{company} OA {type_label} — {label}"


def _clean_doc_source_name(stem: str, company: str, round_type: str, content_type: str) -> str:
    """Generate a readable source_name from a filename stem."""
    # Clean up: replace hyphens/underscores with spaces, strip extra whitespace
    name = re.sub(r"[-_]+", " ", stem).strip()
    # Remove long technical suffixes (e.g. CodeSignal lab names)
    name = re.sub(r"\s*(codesignal|skills evaluation lab|technical brief)\s*", " ", name, flags=re.IGNORECASE).strip()
    name = name[:80]
    type_label = {"pdf_document": "PDF", "csv_dataset": "Dataset", "article": "Doc"}.get(content_type, "Doc")
    return f"{company} {round_type} {type_label} — {name}"


# ── Main extractor ────────────────────────────────────────────────────

def extract_all(raw_dir: Path = RAW_DIR, force: bool = False) -> int:
    """
    Process all unextracted image/PDF/txt/csv files under raw_dir.
    Images grouped by timestamp are merged into single enriched documents.
    Returns number of groups/files processed.
    """
    # ── Group images by timestamp ─────────────────────────────────────
    dir_images: dict[Path, list[Path]] = defaultdict(list)
    for path in sorted(raw_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            dir_images[path.parent].append(path)

    image_groups: list[tuple[Path, list[Path]]] = []
    for parent, images in dir_images.items():
        for key, paths in _group_images_by_timestamp(images).items():
            base = paths[0]
            output = base.with_name(base.name + ".extracted.json")
            if output.exists() and not force:
                continue
            image_groups.append((base, paths))

    # ── Non-image targets ─────────────────────────────────────────────
    non_image: list[Path] = []
    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".pdf", ".txt"} | CSV_EXTS:
            continue
        output = path.with_name(path.name + ".extracted.json")
        if output.exists() and not force:
            continue
        non_image.append(path)

    total = len(image_groups) + len(non_image)
    if total == 0:
        log.info("No new files to extract.")
        return 0

    log.info(f"Extracting {len(image_groups)} image group(s) + {len(non_image)} non-image file(s)…")
    processed = 0

    # ── Image groups ──────────────────────────────────────────────────
    for i, (base_path, paths) in enumerate(image_groups):
        company, round_type = _infer_metadata(base_path, raw_dir)
        group_key = _timestamp_group_key(base_path.stem)
        n = len(paths)
        log.info(f"  [{i+1}/{len(image_groups)}] {group_key!r} ({n} screen{'s' if n > 1 else ''})")

        parts: list[dict] = []
        failed = False
        for img_path in paths:
            try:
                result, backend = _extract_image(img_path)
                parts.append(result)
                log.debug(f"    [{backend}] {img_path.name}: {result.get('question_type','?')} | {result.get('question_summary','')[:60]}")
            except Exception as e:
                log.warning(f"  Failed {img_path.name}: {e}")
                failed = True
                break

        if failed:
            continue

        # Drop pure UI noise screens
        content_parts = [p for p in parts if p.get("question_type") != "ui_noise" and p.get("content", "").strip()]
        if not content_parts:
            log.warning(f"  Skipped {group_key}: all screens are UI noise")
            continue

        merged_content = "\n\n---\n\n".join(p["content"] for p in content_parts)

        # Union topics, deduplicated preserving order
        seen_topics: set[str] = set()
        all_topics: list[str] = []
        for p in content_parts:
            for t in p.get("topics", []):
                if t.lower() not in seen_topics:
                    all_topics.append(t)
                    seen_topics.add(t.lower())

        best_summary = next((p["question_summary"] for p in content_parts if p.get("question_summary")), "")
        question_type = content_parts[0].get("question_type", "other")
        difficulty = content_parts[0].get("difficulty", "")

        if len(merged_content) < 50:
            log.warning(f"  Skipped {group_key}: insufficient content")
            continue

        doc = {
            "id":               hashlib.md5(str(base_path).encode()).hexdigest()[:16],
            "source_type":      "image_ocr",
            "content_type":     "oa_screenshot",
            "content":          merged_content,
            "char_count":       len(merged_content),
            "company":          company,
            "round_type":       round_type,
            "url":              f"local:{base_path.name}",
            "source_name":      _make_source_name(company, question_type, all_topics, best_summary),
            "original_file":    base_path.name,
            "scraped_at":       "",
            "question_type":    question_type,
            "topics":           all_topics,
            "question_summary": best_summary,
            "difficulty":       difficulty,
            "screen_count":     n,
        }

        output = base_path.with_name(base_path.name + ".extracted.json")
        output.write_text(json.dumps(doc, ensure_ascii=False, indent=2))
        log.info(f"    → {len(merged_content)} chars | {question_type} | topics: {all_topics[:3]}")

        # Remove stale per-variant extracted JSONs to avoid double-indexing
        for variant in paths[1:]:
            stale = variant.with_name(variant.name + ".extracted.json")
            if stale.exists():
                stale.unlink()
                log.debug(f"    removed stale: {stale.name}")

        processed += 1

    # ── Non-image files ───────────────────────────────────────────────
    for i, path in enumerate(non_image):
        suffix = path.suffix.lower()
        company, round_type = _infer_metadata(path, raw_dir)
        try:
            if suffix == ".pdf":
                log.info(f"  [pdf] {path.name}")
                content = _extract_pdf(path)
                source_type, content_type = "pdf", "pdf_document"
            elif suffix in CSV_EXTS:
                log.info(f"  [csv] {path.name}")
                content = _extract_csv(path)
                source_type, content_type = "article", "csv_dataset"
            else:
                log.info(f"  [txt] {path.name}")
                content, content_type = _extract_txt(path)
                source_type = "article"
        except Exception as e:
            log.warning(f"  Failed {path.name}: {e}")
            continue

        if not content or len(content) < 50:
            log.warning(f"  Skipped {path.name}: empty")
            continue

        doc = {
            "id":            hashlib.md5(str(path).encode()).hexdigest()[:16],
            "source_type":   source_type,
            "content_type":  content_type,
            "content":       content,
            "char_count":    len(content),
            "company":       company,
            "round_type":    round_type,
            "url":           f"local:{path.name}",
            "source_name":   _KNOWN_SOURCE_NAMES.get(path.stem) or _clean_doc_source_name(path.stem, company, round_type, content_type),
            "original_file": path.name,
            "scraped_at":    "",
        }

        output = path.with_name(path.name + ".extracted.json")
        output.write_text(json.dumps(doc, ensure_ascii=False, indent=2))
        log.info(f"    → {len(content)} chars → {output.name}")
        processed += 1

    log.info(f"Done — {processed}/{total} item(s) extracted.")
    return processed


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent.parent / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    force = "--force" in sys.argv
    extract_all(force=force)
