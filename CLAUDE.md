# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A multimodal RAG system for BCG X / McKinsey QuantumBlack Data Scientist interview prep. It scrapes 60+ sources (forums, Reddit, YouTube, TeamBlind, Glassdoor), chunks and embeds them, then serves hybrid retrieval + Claude-generated answers via a streaming FastAPI/React app.

**Domain filter is strict**: DS/Analytics roles only. Content matching `DE_EXCLUDE_KEYWORDS` (Spark, Kafka, Airflow, dbt, etc.) is discarded at scrape time via `src/scraping/scraper_config.py`.

## Commands

### Backend

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Scrape data (30-60 min full run)
cd src/scraping
python run_all.py                  # All 5 phases
python run_all.py --reddit         # Single phase
python data_inventory.py           # Validate scraped records

# Build vector index (must run after scraping)
cd /home/josh/Zindi/advanced-rag
python build_index.py              # → data/embeddings/{faiss.index, bm25.pkl, chunks.json}

# Run API server
uvicorn src.api.main:app --reload --port 8000
curl http://localhost:8000/api/health
curl http://localhost:8000/api/stats
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build
npm run lint
```

### Environment

```bash
# Required in .env (root)
ANTHROPIC_API_KEY=...
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=...
# Optional
GLASSDOOR_EMAIL=...
GLASSDOOR_PASSWORD=...
```

## Architecture

### Data Flow

```
Scraping (src/scraping/) → data/raw/{company}/{round_type}/*.json
    ↓  build_index.py
Processing (src/processing/) → chunks with metadata
    ↓
FAISS + BM25 index (data/embeddings/)
    ↓
Retriever (src/rag/retriever.py) → top-6 reranked chunks
    ↓
Generator (src/rag/generator.py) → SSE-streamed Claude response
    ↓
FastAPI POST /api/chat → React frontend
```

### Scraping (5 Phases)

All targets and keywords live in `src/scraping/scraper_config.py`.

- **Phase 1** (`forum_scraper.py`): Static pages via `requests`+`trafilatura`; JS-rendered SPAs via Playwright+stealth. Routing controlled by `requires_js=True` flag in `STATIC_TARGETS`.
- **Phase 2** (`reddit_scraper.py`): PRAW with `replace_more(limit=None)` for full thread expansion.
- **Phase 3** (`youtube_scraper.py`): Downloads full MP4s to `data/raw/_youtube_videos/` (permanent), transcribes with Whisper (`WHISPER_MODEL = "base"`).
- **Phase 4** (`teamblind_scraper.py`): Playwright+stealth against Cloudflare.
- **Phase 5** (`reddit_scraper.py → GlassdoorScraper`): `headless=False` + multi-selector login + trafilatura fallback. DOM selectors change frequently.

All records share the same JSON schema: `{id, source_name, url, company, round_type, source_type, scraped_at, content, char_count}`.

### RAG Pipeline

**Embedder** (`src/rag/embedder.py`): `BAAI/bge-small-en-v1.5` with query prefix `"Represent this sentence for searching relevant passages: "`. L2-normalized for FAISS inner-product = cosine similarity.

**Retriever** (`src/rag/retriever.py`) — four-stage hybrid:
1. **Multi-query expansion**: Claude generates 3 query variants
2. **HyDE**: Claude generates a hypothetical answer; embed it alongside original query
3. **Dual search**: BM25 + FAISS on every query/HyDE variant
4. **RRF fusion** (k=60) → cross-encoder reranking (`ms-marco-MiniLM-L-6-v2`) on top-40 candidates → deduplicated top-6

**Generator** (`src/rag/generator.py`): `claude-sonnet-4-6` with prompt caching on system prompt (`"cache_control": {"type": "ephemeral"}`). Streams via `client.messages.stream()`.

### API

`POST /api/chat` accepts `{query, company, round_type, use_hyde, use_multi_query}` and returns SSE events: `{type: "sources" | "token" | "done" | "error"}`. Sources are sent first so the frontend can render attribution before the answer streams in.

### Frontend

`src/hooks/useChat.ts` manages SSE parsing, message state, and abort control. Company ("Both"|"BCG"|"McKinsey") and round ("All"|"General"|"OA"|"Technical"|"LiveCoding"|"Case"|"PEI"|"TakeHome") filters are sent per-request — filtering happens server-side in the vector store, not client-side.

## Key Conventions

- **Full thread extraction is mandatory**. Partial threads have near-zero RAG value — the scrapers are designed to expand all comments.
- **Chunking**: 400 tokens / 80-token overlap via `tiktoken` (cl100k_base). Every chunk carries full source metadata for attribution.
- **Adding sources**: Edit `STATIC_TARGETS`, `REDDIT_SEARCHES`, `YOUTUBE_SEARCHES`, etc. in `scraper_config.py`. No code changes needed for new URLs.
- `data/` is gitignored. Only `src/`, `frontend/src/`, `build_index.py`, and config files are tracked.
