"""
Groq-powered answer generator with streaming.
System prompt is fetched from Langfuse (prompt management) with a hardcoded fallback.
"""

import logging
import os
from typing import Iterator, Optional

from groq import Groq
from langfuse import observe

from .langfuse_client import get_langfuse

log = logging.getLogger(__name__)

GENERATION_MODEL = "llama-3.3-70b-versatile"

_FALLBACK_SYSTEM_PROMPT = """You are an expert interview coach specializing in BCG X (BCG Gamma) and McKinsey QuantumBlack data science recruitment. You have deep knowledge of their interview processes from real candidate experiences.

Your answers are:
- Grounded strictly in the provided context (real experiences, reviews, forum posts)
- Specific: name actual rounds, tools, question types, difficulty levels
- Actionable: give concrete preparation tips
- Honest about uncertainty: if context is sparse, say so

Always cite your sources by mentioning the type (e.g., "According to a Glassdoor review...", "A Reddit thread mentions...", "Based on a YouTube walkthrough...").

Sources marked ⚠ CONFLICT contain information that contradicts another source. When referencing these, acknowledge the discrepancy (e.g., "Reports vary — some candidates mention X while others say Y").
"""

SOURCE_ICONS = {
    "reddit":    "Reddit",
    "glassdoor": "Glassdoor",
    "youtube":   "YouTube",
    "forum":     "Forum",
    "article":   "Article",
    "teamblind": "TeamBlind",
}


def _get_client() -> Groq:
    return Groq(api_key=os.environ["GROQ_API_KEY"])


def _get_system_prompt() -> str:
    """
    Fetch the system prompt from Langfuse prompt management.
    Falls back to the hardcoded prompt if Langfuse is not configured or the prompt
    doesn't exist yet (first run).
    """
    lf = get_langfuse()
    if lf is None:
        return _FALLBACK_SYSTEM_PROMPT

    try:
        prompt_obj = lf.get_prompt("rag-system-prompt", fallback=_FALLBACK_SYSTEM_PROMPT)
        compiled = prompt_obj.compile()
        return compiled if isinstance(compiled, str) else _FALLBACK_SYSTEM_PROMPT
    except Exception as e:
        log.debug(f"Langfuse prompt fetch failed (using fallback): {e}")
        return _FALLBACK_SYSTEM_PROMPT


def _format_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = SOURCE_ICONS.get(chunk.get("source_type", ""), "Source")
        name = chunk.get("source_name", chunk.get("url", "Unknown"))
        company = chunk.get("company", "")
        round_type = chunk.get("round_type", "")
        conflict_tag = f" ⚠ CONFLICT({chunk['_conflict_type']})" if chunk.get("_conflict") else ""
        label = f"{source} | {company} | {round_type} | {name}{conflict_tag}"
        parts.append(f"[Source {i}: {label}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


@observe(as_type="generation", name="generate_answer")
def generate(
    query: str,
    chunks: list[dict],
    company_filter: Optional[str] = None,
    round_filter: Optional[str] = None,
    stream: bool = True,
) -> Iterator[str] | str:
    client = _get_client()
    context = _format_context(chunks)
    system_prompt = _get_system_prompt()

    company_ctx = f" for {company_filter}" if company_filter and company_filter != "Both" else ""
    round_ctx = f" ({round_filter} round)" if round_filter and round_filter != "All" else ""

    user_message = (
        f"Question{company_ctx}{round_ctx}: {query}\n\n"
        f"<context>\n{context}\n</context>\n\n"
        "Based strictly on the context above, provide a comprehensive answer. "
        "Structure your response with clear sections if the answer is multi-part."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_message},
    ]

    if stream:
        def _stream() -> Iterator[str]:
            completion = client.chat.completions.create(
                model=GENERATION_MODEL,
                messages=messages,
                max_tokens=1500,
                stream=True,
            )
            for chunk in completion:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        return _stream()
    else:
        resp = client.chat.completions.create(
            model=GENERATION_MODEL,
            messages=messages,
            max_tokens=1500,
        )
        return resp.choices[0].message.content
