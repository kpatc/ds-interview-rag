# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python data collection pipeline that scrapes interview preparation content for BCG X (Gamma) and McKinsey QuantumBlack **data science and analytics** roles. Feeds a downstream RAG system. Phase 1 (scraping) is fully implemented; `processing/` and `rag/` sibling modules are not yet built.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

Create a `.env` file in the project root:
```
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=advanced-rag-scraper/2.0 by u/USERNAME
GLASSDOOR_EMAIL=...        # optional — for Glassdoor auto-login
GLASSDOOR_PASSWORD=...     # optional
```

## Running the Pipeline

```bash
# From src/scraping/
python run_all.py                          # Full pipeline (Phase 1–5)
python run_all.py --forums                 # Static articles + forum threads
python run_all.py --reddit                 # Reddit full threads (PRAW)
python run_all.py --youtube                # YouTube MP4 download + Whisper
python run_all.py --teamblind              # TeamBlind discussions (Playwright)
python run_all.py --glassdoor              # Glassdoor (headless=False + login)
python run_all.py --glassdoor-manual FILE  # Parse manually exported Glassdoor HTML
python run_all.py --no-whisper             # YouTube without transcription
python run_all.py --check                  # Show data inventory only
```

## Architecture — 5 Scraping Phases

### Phase 1 — Forums & Articles (`forum_scraper.py`)
- **`FullThreadScraper`**: `requests` + `trafilatura` for static pages (igotanoffer, managementconsulted, datalemur, etc.)
- **`PlaywrightForumScraper`**: Playwright + `playwright-stealth` for React SPAs (PrepLounge forums, Grapevine, Quora, InterviewQuery, levels.fyi)
- Domain-specific extractors for PrepLounge, Grapevine, DataLemur, Quora, levels.fyi, InterviewQuery
- Routing: `requires_js=True` in `scraper_config.py` → Playwright path; otherwise static

### Phase 2 — Reddit (`reddit_scraper.py`)
- PRAW with full comment expansion (`replace_more(limit=None)`)
- 28 configured searches across r/datascience, r/consulting, r/cscareerquestions, r/analytics, r/MachineLearning
- `GlassdoorScraper` also lives here — multi-selector login + review extraction

### Phase 3 — YouTube (`youtube_scraper.py`)
- Downloads **full MP4 videos** to `data/raw/_youtube_videos/` (kept permanently)
- Transcribes with local Whisper (`WHISPER_MODEL = "base"`) — Whisper reads MP4 directly
- 21 search queries covering all interview rounds for both companies
- `video_path` field in JSON record points to the MP4 file

### Phase 4 — TeamBlind (`teamblind_scraper.py`)
- New dedicated scraper: search page → post links → full post + comments
- 15 configured searches in `TEAMBLIND_SEARCHES`
- Requires `playwright-stealth` — TeamBlind has Cloudflare anti-bot

### Phase 5 — Glassdoor (`reddit_scraper.py → GlassdoorScraper`)
- `headless=False` + stealth + multi-selector login (Glassdoor changes DOM regularly)
- 5 target company pages, 3–5 pages each
- Falls back to `trafilatura` if selectors miss
- Manual export supported via `--glassdoor-manual`

## Configuration (`scraper_config.py`)

All targets, keywords, and search configs live here:
- `DS_INCLUDE_KEYWORDS` / `DE_EXCLUDE_KEYWORDS` — relevance filter (analytics roles included)
- `STATIC_TARGETS` — 45+ article/forum URLs with `requires_js` flag
- `TEAMBLIND_SEARCHES` — 15 TeamBlind search queries
- `REDDIT_SEARCHES` — 28 subreddit + query tuples
- `YOUTUBE_SEARCHES` — 21 search queries; `YOUTUBE_MAX_DURATION_SECONDS = 2700`
- `GLASSDOOR_TARGETS` — 5 review pages
- `WHISPER_MODEL = "base"` — swap to `"small"` or `"medium"` for better accuracy

## Output Format

All data: `data/raw/{company}/{round_type}/*.json`

Standard record schema:
```json
{
  "id": "md5-hash",
  "source_name": "...",
  "url": "...",
  "company": "BCG|McKinsey|Both",
  "round_type": "General|OA|Technical|LiveCoding|Case|PEI|TakeHome",
  "source_type": "article|forum|reddit|youtube|glassdoor|teamblind",
  "scraped_at": "ISO timestamp",
  "content": "full text",
  "char_count": 0,
  "video_path": "path/to/file.mp4"   // YouTube records only
}
```

YouTube videos: `data/raw/_youtube_videos/{video_id}.mp4`

`data_inventory.py` validates all records (flags < 300 chars or > 100k chars) and writes `manifest.json`.

## Key Design Constraints

- **DS/Analytics filter is strict**: DE keywords (Spark, Kafka, Airflow, dbt...) exclude content even on DS-adjacent pages. Analytics roles (data analyst, analytics consultant) are included.
- **Full thread extraction is required**: Partial threads have near-zero RAG value — always fetch all replies/comments.
- **Videos are kept**: Unlike the old audio-only approach, MP4 files are stored permanently in `_youtube_videos/`.
- **PrepLounge forums are React SPAs**: Must use `requires_js=True` for `/consulting-forum/` URLs; bootcamp article pages work with static requests.
- **Glassdoor DOM changes**: Use multi-selector approach + trafilatura fallback; `headless=False` bypasses bot detection.
- **TeamBlind needs stealth**: `playwright-stealth` is required; without it Cloudflare will block headless Chromium.
