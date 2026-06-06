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
from typing import AsyncIterator, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from api.schemas import ChatRequest, IndexStats, HealthResponse
from rag.retriever import retrieve
from rag.generator import generate
from rag.vectorstore import CHUNKS_FILE, FAISS_FILE

log = logging.getLogger("api")
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="DS Interview RAG API",
    description="Multimodal RAG for BCG X & McKinsey QuantumBlack DS interview prep",
    version="1.0.0",
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


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not FAISS_FILE.exists():
        raise HTTPException(503, "Index not built yet — run build_index.py")

    company = req.company if req.company != "Both" else None
    round_type = req.round_type if req.round_type != "All" else None

    try:
        chunks = retrieve(
            query=req.query,
            top_k=6,
            company_filter=company,
            round_filter=round_type,
            use_hyde=req.use_hyde,
            use_multi_query=req.use_multi_query,
        )
    except Exception as e:
        log.error(f"Retrieval failed: {e}")
        raise HTTPException(500, f"Retrieval error: {e}")

    sources = [
        {
            "source_name": c.get("source_name", ""),
            "source_type": c.get("source_type", ""),
            "company": c.get("company", ""),
            "round_type": c.get("round_type", ""),
            "url": c.get("url", ""),
            "score": round(c.get("_score", 0), 3),
            "excerpt": c["text"][:220] + "…" if len(c["text"]) > 220 else c["text"],
        }
        for c in chunks
    ]

    async def event_stream() -> AsyncIterator[str]:
        # Send sources first as a metadata event
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

        # Stream the answer
        try:
            for token in generate(
                query=req.query,
                chunks=chunks,
                company_filter=req.company,
                round_filter=req.round_type,
                stream=True,
            ):
                yield f"data: {json.dumps({'type': 'token', 'text': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
