"""
Cross-Checker Agent: detects factual, temporal, and scope conflicts between retrieved chunks.
Annotates chunks with _trust_score, _conflict, _conflict_type, _conflict_note.
Uses Groq llama-3.1-8b-instant for fast, cheap conflict detection.
"""

import json
import logging
import os

from groq import Groq
from langfuse import observe

log = logging.getLogger(__name__)

_CHECK_MODEL = "llama-3.1-8b-instant"

_TRUST_BY_SOURCE: dict[str, float] = {
    "glassdoor":  0.90,
    "article":    0.85,
    "youtube":    0.75,
    "reddit":     0.65,
    "forum":      0.60,
    "teamblind":  0.55,
}

_CONFLICT_PROMPT = """\
You are a fact-checker for interview preparation content about BCG X and McKinsey QuantumBlack data science roles.

Below are {n} retrieved text chunks (indexed 0 to {n_minus_1}). Identify ONLY clear, significant conflicts — not minor differences in emphasis or phrasing.

Conflict types:
- HARD: Contradictory facts (e.g., different OA durations, different number of rounds, different difficulty ratings)
- TEMPORAL: Older information contradicts newer (flag the older chunk as conflicting)
- SCOPE: Information about BCG labeled as McKinsey or vice versa

Output ONLY valid JSON, no other text:
{{"conflicts": [
  {{"chunk_ids": [0, 2], "type": "HARD", "note": "one-sentence description of the conflict"}},
  ...
]}}

If no significant conflicts: {{"conflicts": []}}

Chunks:
{chunks_text}
"""


def _trust_score(chunk: dict) -> float:
    base = _TRUST_BY_SOURCE.get(chunk.get("source_type", ""), 0.50)
    scraped = (chunk.get("scraped_at") or "")[:4]
    if scraped >= "2024":
        base = min(base + 0.05, 1.0)
    return round(base, 2)


def _format_for_check(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks):
        company = c.get("company", "")
        round_t = c.get("round_type", "")
        src = c.get("source_type", "unknown")
        date = (c.get("scraped_at") or "")[:10] or "unknown"
        header = f"[{i}] {src} | {company} | {round_t} | {date}"
        parts.append(f"{header}\n{c['text'][:500]}")
    return "\n\n---\n\n".join(parts)


@observe(as_type="span", name="cross_check")
def cross_check(chunks: list[dict]) -> list[dict]:
    """
    Annotate each chunk with conflict metadata and trust score.
    Non-fatal: if Groq call fails, returns chunks with defaults.
    """
    for c in chunks:
        c["_trust_score"] = _trust_score(c)
        c["_conflict"] = False
        c["_conflict_type"] = ""
        c["_conflict_note"] = ""

    if len(chunks) < 2:
        return chunks

    try:
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        prompt = _CONFLICT_PROMPT.format(
            n=len(chunks),
            n_minus_1=len(chunks) - 1,
            chunks_text=_format_for_check(chunks),
        )
        resp = client.chat.completions.create(
            model=_CHECK_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        for conflict in data.get("conflicts", []):
            ids = conflict.get("chunk_ids", [])
            ctype = conflict.get("type", "HARD")
            note = conflict.get("note", "")
            for idx in ids:
                if 0 <= idx < len(chunks):
                    chunks[idx]["_conflict"] = True
                    chunks[idx]["_conflict_type"] = ctype
                    chunks[idx]["_conflict_note"] = note

        n_conflicts = sum(1 for c in chunks if c["_conflict"])
        if n_conflicts:
            log.info(f"Cross-checker found {n_conflicts} conflicting chunk(s)")

    except Exception as e:
        log.warning(f"Cross-checker failed (non-fatal): {e}")

    return chunks
