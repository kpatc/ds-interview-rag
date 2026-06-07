<div align="center">

# DS Interview Coach

**An advanced agentic RAG system for BCG X & McKinsey QuantumBlack Data Science interview preparation**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Groq](https://img.shields.io/badge/LLM-Groq%20Llama%203.3-orange?logo=groq&logoColor=white)](https://groq.com)
[![Langfuse](https://img.shields.io/badge/Observability-Langfuse-purple)](https://langfuse.com)

*Answers grounded in 900+ chunks from forums, Reddit, Glassdoor, YouTube, and real OA screenshots — with automatic conflict detection, quality gating, and full LLM observability*

</div>

---

## What It Does

DS Interview Coach is a **production-grade agentic RAG system** that answers interview preparation questions for **BCG X (formerly BCG Gamma)** and **McKinsey QuantumBlack** Data Science & Analytics roles. Unlike generic prep resources, every answer is:

- Sourced from real candidate experiences, Glassdoor reviews, YouTube walkthroughs, and actual OA screenshots
- Cross-checked for conflicts between sources by a dedicated agent
- Quality-scored on 4 dimensions, with automatic re-retrieval if the answer falls below threshold
- Fully observable in Langfuse — every LLM call, retrieval step, and critic score is traced

**Filter by company and round type** — get targeted answers for OA, Technical, Live Coding, Case, PEI, or Take-Home rounds.

---

## Screenshots

### Main Interface
![DS Interview Coach UI](docs/chatui.png)

*Left sidebar shows company filter (BCG X / McKinsey QB), round type, and live index stats. Sources panel shows trust scores and conflict warnings.*

### Example Conversation
![Example Chat Response](docs/examplechat.png)

*Streaming answer with structured breakdown of the BCG X CodeSignal OA format — probability/statistics questions, ML concepts, and coding challenges — sourced from actual candidate reports.*

---

## Architecture — Agentic RAG Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER QUERY                                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   RETRIEVER AGENT   │  src/rag/retriever.py
                    │                     │
                    │ 1. Multi-query       │  → Groq Llama 3.3: 3 query variants
                    │ 2. HyDE             │  → Groq: hypothetical answer → embed
                    │ 3. Dual search      │  → BM25 + FAISS (bge-large-en-v1.5)
                    │ 4. RRF fusion k=60  │  → Reciprocal rank fusion
                    │ 5. Cross-encoder    │  → ms-marco-MiniLM-L-12-v2 rerank
                    └──────────┬──────────┘
                               │  top-6 chunks
                    ┌──────────▼──────────┐
                    │  CROSS-CHECKER AGENT│  src/rag/cross_checker.py
                    │                     │
                    │ · Groq detects      │  → HARD / TEMPORAL / SCOPE conflicts
                    │   conflicts in      │  → Trust hierarchy by source type
                    │   one pass          │  → Annotates chunks: _conflict,
                    │ · Trust scores:     │     _conflict_type, _conflict_note,
                    │   glassdoor 0.90    │     _trust_score
                    │   article   0.85    │
                    │   youtube   0.75    │
                    │   reddit    0.65    │
                    └──────────┬──────────┘
                               │  annotated chunks
                    ┌──────────▼──────────┐
                    │   GENERATOR AGENT   │  src/rag/generator.py
                    │                     │
                    │ · Groq Llama 3.3    │  → Prompt from Langfuse or fallback
                    │ · Conflict-aware    │  → ⚠ CONFLICT tag in context
                    │   system prompt     │  → SSE token streaming
                    └──────────┬──────────┘
                               │  streamed answer
                    ┌──────────▼──────────┐
                    │    CRITIC AGENT     │  src/rag/critic.py
                    │   (Quality Gate)    │
                    │                     │
                    │ Coverage    30%     │  → Scores 0–10 per dimension
                    │ Src Quality 30%     │  → Weighted score threshold: 7.5/10
                    │ Specificity 20%     │  → Generates improved queries
                    │ Actionability 20%   │     if quality gate fails
                    └──────────┬──────────┘
                               │
              ┌────────────────┴──────────────────┐
              │                                   │
        score ≥ 7.5                         score < 7.5
              │                                   │
         ✅ DONE                    ┌─────────────▼─────────────┐
                                    │   REFINEMENT PASS         │
                                    │ · Re-retrieve top-8       │
                                    │ · Merge with original     │
                                    │ · Re-generate + re-score  │
                                    └───────────────────────────┘
```

---

## Observability — Langfuse Integration

Every request is fully traced in [Langfuse](https://langfuse.com):

```
Trace: rag_chat
  ├── Span: hybrid_retrieve      ← query variants, FAISS+BM25 results, reranking scores
  ├── Span: cross_check          ← conflict flags, trust scores per chunk
  ├── Generation: generate_answer ← model, tokens, latency, system prompt version
  ├── Evaluator: critic_gate     ← 4-dimension scores, gaps, improved queries
  └── Score: critic_score        ← numeric quality score attached to trace
```

**What's traced automatically (zero extra code):**
- All Groq API calls via `GroqInstrumentor` — model, messages, token counts, latency
- `@observe` decorators on all 4 pipeline functions
- Per-request metadata: company filter, round type → visible on every child span

**Prompt management:** The generator system prompt is fetched live from Langfuse. Update it in the UI without restarting the API.

---

## Evaluation — Ragas Pipeline

`eval/run_eval.py` runs 5 reference-based metrics on a 20-question golden test set:

| Metric | What it measures |
|--------|-----------------|
| **Faithfulness** | Does the answer stay grounded in the retrieved chunks? |
| **Answer Relevancy** | How relevant is the answer to the question? |
| **Context Precision** | Are the retrieved chunks actually useful for the answer? |
| **Context Recall** | Did retrieval capture all the information needed? |
| **Answer Correctness** | How factually correct is the answer vs. the reference? |

```bash
# Run full eval (saves results to eval/results/)
python eval/run_eval.py

# Save current scores as regression baseline
python eval/run_eval.py --save-baseline

# Quick check (5 questions)
python eval/run_eval.py --subset 5

# Target a specific round
python eval/run_eval.py --company BCG --round OA
```

**Regression gate:** Any metric dropping >5% from baseline exits with code 1 — ready to plug into CI.

---

## Data Sources

| Source | Type | Content |
|--------|------|---------|
| Glassdoor BCG & McKinsey | Reviews | 138 interview reviews |
| Reddit (r/datascience, r/consulting…) | Threads | 449 chunks, full comment trees |
| YouTube | Transcripts | 21 videos, Whisper-transcribed |
| OA Screenshots | Vision OCR | 30 chunks — real CodeSignal & HackerRank questions |
| DataInterview, HackingTheCaseInterview | Articles | Detailed role-specific guides |
| DataLemur Q&A | Technical Q&A | Per-question retrieval with topic tagging |
| PDFs & Take-Home Cases | Documents | BCG X official materials |

> **Domain filter is strict**: Data Engineering content (Spark, Kafka, Airflow, dbt…) is excluded at scrape time. Only DS/Analytics roles are indexed.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Embeddings | `BAAI/bge-large-en-v1.5` (1024-dim, L2-normalized) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-12-v2` |
| LLM (generation, query expansion, HyDE) | Groq `llama-3.3-70b-versatile` |
| LLM (conflict detection) | Groq `llama-3.1-8b-instant` |
| OA vision extraction | Gemini 2.5 Flash → Groq Llama 4 Scout fallback |
| Vector store | FAISS (inner product = cosine) + rank-bm25 |
| Observability | Langfuse + GroqInstrumentor (OpenTelemetry) |
| Evaluation | Ragas 0.4 (faithfulness, relevancy, precision, recall, correctness) |
| Backend | FastAPI · Python 3.11 |
| Frontend | React 18 · TypeScript · Vite |

---

## API

`POST /api/chat` — returns SSE stream

```json
// Request
{
  "query": "How does the BCG X CodeSignal OA work?",
  "company": "BCG",
  "round_type": "OA",
  "use_hyde": true,
  "use_multi_query": true
}
```

```
// Response (SSE)
data: {"type": "sources", "sources": [...], "trace_id": "abc123"}
data: {"type": "token", "text": "The BCG X..."}
data: {"type": "quality", "score": 8.2, "pass": true, "dimensions": {...}, "gaps": [...]}
data: {"type": "refining", "reason": "...", "query": "..."}   ← only if quality gate fails
data: {"type": "token", "text": "..."}                        ← refined answer tokens
data: {"type": "done"}
```

`GET /api/health` — index readiness check  
`GET /api/stats` — chunk counts by company, source type, and round

---

## Setup

### Prerequisites

```bash
pip install -r requirements.txt
playwright install chromium
```

### Environment variables (`.env` in root)

```env
ANTHROPIC_API_KEY=...       # unused in current stack, kept for future
GROQ_API_KEY=...            # generation, query expansion, critic, cross-checker
GEMINI_API_KEY=...          # OA screenshot vision extraction
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=...

# Langfuse (optional — tracing disabled gracefully if absent)
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### Build the index

```bash
# Option A — use pre-scraped data (if data/raw/ is populated)
python build_index.py

# Option B — scrape from scratch (~1h) then index
cd src/scraping && python run_all.py
cd ../.. && python build_index.py
```

### Run

```bash
# Backend
uvicorn src.api.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
# → http://localhost:5173
```

---

## Example Questions

| Question | Company | Round |
|----------|---------|-------|
| *"What is the BCG X CodeSignal OA format and how hard is it?"* | BCG X | OA |
| *"Walk me through McKinsey QuantumBlack technical interview expectations"* | McKinsey QB | Technical |
| *"How does the BCG X take-home case assignment work?"* | BCG X | Take-Home |
| *"What stories should I prepare for a McKinsey PEI round?"* | McKinsey QB | PEI |
| *"What Python and SQL skills does BCG X actually test in the pair programming round?"* | BCG X | Live Coding |
| *"How is the McKinsey HackerRank OA structured compared to BCG CodeSignal?"* | Both | OA |

---

## Project Structure

```
├── build_index.py              # Build FAISS + BM25 index from raw data
├── eval/
│   ├── run_eval.py             # Ragas evaluation pipeline + regression gate
│   └── golden_set.json         # 20-question annotated test set
├── src/
│   ├── scraping/               # 5-phase scraper (forums, Reddit, YouTube, TeamBlind, Glassdoor)
│   │   └── scraper_config.py   # All targets, keywords, search configs
│   ├── processing/
│   │   ├── multimodal.py       # Gemini vision extraction for OA screenshots, PDFs
│   │   ├── chunker.py          # Adaptive chunking with Q&A splitting
│   │   └── loader.py           # Document loading, quality scoring, per-source filtering
│   ├── rag/
│   │   ├── retriever.py        # 4-stage hybrid retrieval (multi-query + HyDE + RRF + rerank)
│   │   ├── cross_checker.py    # Conflict detection agent (HARD / TEMPORAL / SCOPE)
│   │   ├── generator.py        # Groq streaming with Langfuse prompt management
│   │   ├── critic.py           # Quality gate: 4-dimension scoring + re-retrieval trigger
│   │   ├── langfuse_client.py  # Langfuse singleton + GroqInstrumentor auto-tracing
│   │   └── embedder.py         # bge-large-en-v1.5 with query prefix
│   └── api/
│       ├── main.py             # FastAPI endpoints + SSE streaming
│       └── schemas.py          # Pydantic request/response models
└── frontend/                   # React + TypeScript + Vite
```

---

## License

MIT
