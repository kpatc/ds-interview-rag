"""
Groq-powered answer generator with streaming.
Uses llama-3.3-70b-versatile for generation (free tier, very fast).
"""

import os
from typing import Iterator, Optional

from groq import Groq

GENERATION_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are an expert interview coach specializing in BCG X (BCG Gamma) and McKinsey QuantumBlack data science recruitment. You have deep knowledge of their interview processes from real candidate experiences.

Your answers are:
- Grounded strictly in the provided context (real experiences, reviews, forum posts)
- Specific: name actual rounds, tools, question types, difficulty levels
- Actionable: give concrete preparation tips
- Honest about uncertainty: if context is sparse, say so

Always cite your sources by mentioning the type (e.g., "According to a Glassdoor review...", "A Reddit thread mentions...", "Based on a YouTube walkthrough...").
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


def _format_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        source = SOURCE_ICONS.get(chunk.get("source_type", ""), "Source")
        name = chunk.get("source_name", chunk.get("url", "Unknown"))
        company = chunk.get("company", "")
        round_type = chunk.get("round_type", "")
        label = f"{source} | {company} | {round_type} | {name}"
        parts.append(f"[Source {i}: {label}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


def generate(
    query: str,
    chunks: list[dict],
    company_filter: Optional[str] = None,
    round_filter: Optional[str] = None,
    stream: bool = True,
) -> Iterator[str] | str:
    client = _get_client()
    context = _format_context(chunks)

    company_ctx = f" for {company_filter}" if company_filter and company_filter != "Both" else ""
    round_ctx = f" ({round_filter} round)" if round_filter and round_filter != "All" else ""

    user_message = (
        f"Question{company_ctx}{round_ctx}: {query}\n\n"
        f"<context>\n{context}\n</context>\n\n"
        "Based strictly on the context above, provide a comprehensive answer. "
        "Structure your response with clear sections if the answer is multi-part."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
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
