"""
FastAPI backend — exposes the RAG pipeline over HTTP with SSE streaming.

Run:
    cd /home/josh/Zindi/advanced-rag
    source venv/bin/activate
    uvicorn src.api.main:app --reload --port 8000
"""

import json
import logging
import sys
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langfuse import observe, propagate_attributes

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from api.schemas import ChatRequest, IndexStats, HealthResponse
from rag.retriever import retrieve
from rag.generator import generate
from rag.cross_checker import cross_check
from rag.critic import critique
from rag.vectorstore import CHUNKS_FILE, FAISS_FILE
from rag.langfuse_client import get_langfuse, flush as langfuse_flush

log = logging.getLogger("api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="DS Interview RAG API",
    description="Multimodal RAG for BCG X & McKinsey QuantumBlack DS interview prep",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health():
    index_ready = FAISS_FILE.exists() and CHUNKS_FILE.exists()
    return HealthResponse(status="ok", index_ready=index_ready)


@app.get("/api/stats", response_model=IndexStats)
def stats():
    if not CHUNKS_FILE.exists():
        raise HTTPException(503, "Index not built yet — run build_index.py")
    chunks = json.loads(CHUNKS_FILE.read_text())
    by_company: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_round: dict[str, int] = {}
    for c in chunks:
        by_company[c["company"]] = by_company.get(c["company"], 0) + 1
        by_source[c["source_type"]] = by_source.get(c["source_type"], 0) + 1
        by_round[c["round_type"]] = by_round.get(c["round_type"], 0) + 1
    return IndexStats(
        total_chunks=len(chunks),
        by_company=by_company,
        by_source=by_source,
        by_round=by_round,
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _build_sources(chunks: list[dict]) -> list[dict]:
    return [
        {
            "source_name":   c.get("source_name", ""),
            "source_type":   c.get("source_type", ""),
            "company":       c.get("company", ""),
            "round_type":    c.get("round_type", ""),
            "url":           c.get("url", ""),
            "score":         round(c.get("_score", 0), 3),
            "trust_score":   c.get("_trust_score", 0.8),
            "conflict":      c.get("_conflict", False),
            "conflict_type": c.get("_conflict_type", ""),
            "conflict_note": c.get("_conflict_note", ""),
            "excerpt":       c["text"][:220] + "…" if len(c["text"]) > 220 else c["text"],
        }
        for c in chunks
    ]


@observe(name="rag_chat")
@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not FAISS_FILE.exists():
        raise HTTPException(503, "Index not built yet — run build_index.py")

    company    = req.company    if req.company    != "Both" else None
    round_type = req.round_type if req.round_type != "All"  else None

    lf = get_langfuse()

    # ── Attach per-request metadata to the trace ──
    # propagate_attributes makes company/round visible on every child span
    with propagate_attributes(
        metadata={"company": req.company, "round_type": req.round_type},
        tags=[req.company, req.round_type],
    ):
        trace_id: str | None = lf.get_current_trace_id() if lf else None

        # ── Retrieve + cross-check ──
        try:
            chunks = retrieve(
                query=req.query,
                top_k=6,
                company_filter=company,
                round_filter=round_type,
                use_hyde=req.use_hyde,
                use_multi_query=req.use_multi_query,
            )
            chunks = cross_check(chunks)
        except Exception as e:
            log.error(f"Retrieval/cross-check failed: {e}")
            raise HTTPException(500, f"Retrieval error: {e}")

    async def event_stream() -> AsyncIterator[str]:
        # ── 1. Sources (with conflict annotations + trace_id for frontend correlation) ──
        yield _sse({"type": "sources", "sources": _build_sources(chunks), "trace_id": trace_id})

        # ── 2. First-pass generation — stream tokens AND buffer for critic ──
        answer_buf: list[str] = []
        try:
            for token in generate(
                query=req.query,
                chunks=chunks,
                company_filter=req.company,
                round_filter=req.round_type,
                stream=True,
            ):
                yield _sse({"type": "token", "text": token})
                answer_buf.append(token)
        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})
            yield _sse({"type": "done"})
            return

        answer = "".join(answer_buf)

        # ── 3. Critic quality gate ──
        try:
            crit = critique(req.query, chunks, answer)
        except Exception as e:
            log.warning(f"Critic error (skipping): {e}")
            yield _sse({"type": "done"})
            return

        yield _sse({
            "type": "quality", "score": crit.score, "pass": crit.passed,
            "dimensions": crit.dimensions, "gaps": crit.gaps,
        })

        # Score the trace in Langfuse (create_score works outside the observe context)
        if lf and trace_id:
            lf.create_score(
                trace_id=trace_id,
                name="critic_score",
                value=crit.score,
                data_type="NUMERIC",
                comment=f"pass={crit.passed} | gaps: {'; '.join(crit.gaps[:2])}",
            )

        if crit.passed or not crit.improved_queries:
            langfuse_flush()
            yield _sse({"type": "done"})
            return

        # ── 4. Refinement pass ──
        refined_q = crit.improved_queries[0]
        log.info(f"Quality gate failed ({crit.score:.1f}/10) — refining: {refined_q!r}")
        yield _sse({"type": "refining", "reason": "; ".join(crit.gaps[:2]), "query": refined_q})

        try:
            refined_chunks = retrieve(
                query=refined_q, top_k=8,
                company_filter=company, round_filter=round_type,
                use_hyde=req.use_hyde, use_multi_query=False,
            )
            refined_chunks = cross_check(refined_chunks)

            seen_ids = {c["chunk_id"] for c in refined_chunks}
            for c in chunks:
                if c["chunk_id"] not in seen_ids and len(refined_chunks) < 8:
                    refined_chunks.append(c)
        except Exception as e:
            log.error(f"Refined retrieval failed: {e}")
            yield _sse({"type": "done"})
            return

        answer2_buf: list[str] = []
        try:
            for token in generate(
                query=req.query, chunks=refined_chunks,
                company_filter=req.company, round_filter=req.round_type, stream=True,
            ):
                yield _sse({"type": "token", "text": token})
                answer2_buf.append(token)
        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})
            yield _sse({"type": "done"})
            return

        # ── 5. Second critique (informational only) ──
        try:
            crit2 = critique(req.query, refined_chunks, "".join(answer2_buf))
            yield _sse({
                "type": "quality", "score": crit2.score, "pass": crit2.passed,
                "dimensions": crit2.dimensions, "gaps": crit2.gaps,
            })
            if lf and trace_id:
                lf.create_score(
                    trace_id=trace_id, name="critic_score_refined",
                    value=crit2.score, data_type="NUMERIC",
                )
        except Exception:
            pass

        langfuse_flush()
        yield _sse({"type": "done"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
