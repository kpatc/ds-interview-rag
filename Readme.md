# 🎯 Advanced RAG — BCG X & McKinsey DS Recruitment Coach

> Multimodal chatbot for Data Scientists preparing for BCG X (Gamma) and McKinsey QuantumBlack recruitment processes.
> Combines advanced RAG (text, PDF, images, videos) with curated real-world data.

---

## 🏗️ Architecture

```
advanced-rag/
├── data/
│   ├── raw/                    ← Scraped data (this module)
│   │   ├── bcg/
│   │   │   ├── general/        → General process guides
│   │   │   ├── oa/             → Online Assessment (CodeSignal)
│   │   │   ├── case/           → Business/data cases
│   │   │   ├── takehome/       → Take-home assignments
│   │   │   ├── pei/            → Behavioral interviews
│   │   │   └── livecoding/     → Live/pair coding
│   │   ├── mckinsey/
│   │   │   └── [same structure]
│   │   └── both/               → Cross-company content
│   ├── processed/              ← Chunked + cleaned text
│   └── embeddings/             ← Vector store (FAISS / ChromaDB)
│
├── src/
│   ├── scraping/               ← ✅ THIS MODULE
│   │   ├── scraper_config.py   → All targets (60+ URLs)
│   │   ├── scraper.py          → 4-strategy orchestrator
│   │   └── data_inventory.py   → Quality check + manifest
│   │
│   ├── processing/             ← NEXT: chunking, cleaning
│   │   ├── text_cleaner.py
│   │   ├── pdf_parser.py       → PyMuPDF for PDF extraction
│   │   ├── image_ocr.py        → Tesseract / GPT-4V for screenshots
│   │   └── chunker.py          → Semantic chunking
│   │
│   ├── rag/                    ← RAG pipeline
│   │   ├── embedder.py         → text-embedding-3-small / BGE
│   │   ├── vectorstore.py      → FAISS or ChromaDB
│   │   ├── retriever.py        → Hybrid BM25 + dense retrieval
│   │   └── generator.py        → Claude / GPT-4 synthesis
│   │
│   └── app/                    ← Chatbot UI
│       ├── chatbot.py          → Streamlit or FastAPI
│       └── prompts.py          → System prompts per interview type
│
└── notebooks/
    ├── 01_data_exploration.ipynb
    ├── 02_rag_evaluation.ipynb
    └── 03_demo.ipynb
```

## 🔄 Recruitment Process Coverage

### BCG X (BCG Gamma)
| Round | Platform/Format | What to Expect |
|-------|----------------|----------------|
| **Online Assessment** | CodeSignal | Algo (LeetCode Medium), DS/ML questions, SQL, Stats |
| **Take-Home Case** | Provided CSV + PDF brief | EDA, modeling, slide deck presentation |
| **Technical Interview** | Live call | ML theory, stats, SQL, business problem solving |
| **Pair Programming** | Shared IDE (CoderPad) | Python DS task, code quality, communication |
| **Case Interview** | Consulting framework | Data-driven business case (revenue, cost, market) |
| **PEI / Behavioral** | HR round | Fit questions, motivation, leadership stories |

### McKinsey QuantumBlack
| Round | Platform/Format | What to Expect |
|-------|----------------|----------------|
| **Online Assessment** | McKinsey Solve (gamified) | Ecosystem game, Redrock study, problem-solving |
| **Take-Home Case** | Provided data + brief | Analysis + slide deck (2-3 days) |
| **Technical Interview** | Live call | Statistics, ML, experimentation design |
| **Pair Programming (TEI)** | Python shared screen | Real DS task, think-aloud, pair collaboration |
| **Case Interview** | Quant-heavy | Numbers-first case, market sizing |
| **PEI Interview** | 3 structured stories | Personal impact, entrepreneurial drive, leadership |

## 🚀 Quick Start

### 1. Clone & install
```bash
git clone <repo>
cd advanced-rag
pip install -r src/scraping/requirements.txt
playwright install chromium
```

### 2. Run scraping
```bash
cd src/scraping

# Quick test (static articles only, ~2 min)
python scraper.py --only static

# Reddit + YouTube (requires internet)
python scraper.py --only reddit
python scraper.py --only youtube

# Full scrape (30-60 min)
python scraper.py

# Check what was collected
python data_inventory.py
```

### 3. Add your own data
Drop files in the appropriate folder:
```
data/raw/bcg/oa/          ← Your OA screenshots, notes
data/raw/bcg/case/        ← Your case examples
data/raw/bcg/takehome/    ← Your take-home PDFs, CSVs
data/raw/mckinsey/        ← McKinsey equivalent
```

Supported formats: `.pdf`, `.png`, `.jpg`, `.txt`, `.csv`, `.json`

## 📊 Data Sources (60+ targets)

- **Articles**: datainterview.com, hackingthecaseinterview.com, preplounge.com, interviewquery.com
- **Blogs**: linkjob.ai (CodeSignal 2025), jigfopsda (McKinsey experience), medium
- **Reddit**: r/datascience, r/consulting, r/cscareerquestions, r/MachineLearning
- **YouTube**: Interview walkthroughs, case examples, coding demos (transcripts via yt-dlp)
- **Glassdoor**: BCG X + McKinsey review pages (manual export supported)
- **Your own data**: Screenshots, PDFs, case notes, take-home assignments

## 🧠 RAG Features (roadmap)

- [x] Data collection (scraping module)
- [ ] Multimodal chunking (text + PDF + images)
- [ ] YouTube transcript ingestion
- [ ] Hybrid retrieval (BM25 + dense vectors)
- [ ] Round-aware routing (filter by BCG/McKinsey + round type)
- [ ] Practice mode (mock OA, case simulator)
- [ ] Feedback generation on user answers

## 👨‍💻 Portfolio Notes

This project demonstrates:
- **Advanced RAG**: multimodal (text, PDF, image, video), hybrid retrieval
- **Data engineering**: web scraping (static, JS, Reddit API, YouTube)
- **NLP**: semantic chunking, embedding, retrieval evaluation
- **Product thinking**: domain-specific assistant with real user value