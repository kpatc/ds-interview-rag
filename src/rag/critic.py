"""
Critic Agent (Quality Gate): scores the generated answer on 4 dimensions.
Uses Groq llama-3.3-70b-versatile — free tier, strong enough for evaluation.
Returns CriticResult with score, pass/fail, gaps, and improved queries for re-retrieval.
"""

import json
import logging
import os
from dataclasses import dataclass, field

from groq import Groq
from langfuse import observe

log = logging.getLogger(__name__)

CRITIC_MODEL = "llama-3.3-70b-versatile"
QUALITY_THRESHOLD = 7.5

_CRITIC_PROMPT = """\
You are a quality evaluator for an interview preparation assistant focused on BCG X and McKinsey QuantumBlack data science roles.

## User Query
{query}

## Retrieved Sources ({n_sources} chunks)
{sources_summary}

## Generated Answer
{answer}

## Task
Score the answer on 4 dimensions (0–10 each):

1. **coverage** (weight 30%): Does the answer address all aspects of the query? Are important sub-topics missing?
2. **source_quality** (weight 30%): Are sources reliable, specific, and relevant? Are there enough distinct source types?
3. **specificity** (weight 20%): Concrete details — names, durations, difficulty levels, exact formats?
4. **actionability** (weight 20%): Practical, actionable preparation tips the candidate can act on?

Output ONLY valid JSON (no markdown fences, no extra text):
{{
  "dimensions": {{
    "coverage": <0-10>,
    "source_quality": <0-10>,
    "specificity": <0-10>,
    "actionability": <0-10>
  }},
  "gaps": ["<specific missing info 1>", "<specific missing info 2>"],
  "improved_queries": ["<targeted query to fill gap 1>", "<targeted query to fill gap 2>"]
}}
"""


@dataclass
class CriticResult:
    score: float
    passed: bool
    dimensions: dict[str, float] = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)
    improved_queries: list[str] = field(default_factory=list)


def _sources_summary(chunks: list[dict]) -> str:
    lines = []
    for i, c in enumerate(chunks, 1):
        src = c.get("source_type", "unknown")
        company = c.get("company", "")
        round_t = c.get("round_type", "")
        conflict = " [CONFLICT]" if c.get("_conflict") else ""
        trust = c.get("_trust_score", 0.0)
        lines.append(f"  {i}. {src} | {company} | {round_t} | trust={trust:.2f}{conflict}")
    return "\n".join(lines)


def _weighted_score(dims: dict[str, float]) -> float:
    return round(
        dims.get("coverage", 0) * 0.30
        + dims.get("source_quality", 0) * 0.30
        + dims.get("specificity", 0) * 0.20
        + dims.get("actionability", 0) * 0.20,
        2,
    )


@observe(as_type="evaluator", name="critic_gate")
def critique(query: str, chunks: list[dict], answer: str) -> CriticResult:
    """
    Score the generated answer. Non-fatal: returns a passing result on any error
    so that a critique failure never blocks the user from seeing an answer.
    """
    client = Groq(api_key=os.environ["GROQ_API_KEY"])

    prompt = _CRITIC_PROMPT.format(
        query=query,
        n_sources=len(chunks),
        sources_summary=_sources_summary(chunks),
        answer=answer[:3000],
    )

    try:
        resp = client.chat.completions.create(
            model=CRITIC_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()

        # Strip markdown fences if the model wraps its output
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        dims = data.get("dimensions", {})
        score = _weighted_score(dims)

        log.info(
            f"Critic score: {score:.1f}/10 "
            f"(cov={dims.get('coverage',0):.0f} "
            f"src={dims.get('source_quality',0):.0f} "
            f"spec={dims.get('specificity',0):.0f} "
            f"act={dims.get('actionability',0):.0f})"
        )

        return CriticResult(
            score=score,
            passed=score >= QUALITY_THRESHOLD,
            dimensions=dims,
            gaps=data.get("gaps", [])[:3],
            improved_queries=data.get("improved_queries", [])[:2],
        )

    except Exception as e:
        log.warning(f"Critic failed (non-fatal): {e}")
        return CriticResult(score=QUALITY_THRESHOLD, passed=True)
