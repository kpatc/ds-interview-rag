"""
Build the RAG index from all raw scraped data.
Run once (and re-run after new scraping sessions).

Usage:
    cd /home/josh/Zindi/advanced-rag
    source venv/bin/activate
    python build_index.py
"""

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)-20s] %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_index")

from processing.loader import load_all_documents
from processing.chunker import chunk_all
from rag.vectorstore import build_index


def main():
    t0 = time.time()

    log.info("━━ Step 1: Loading documents ━━")
    docs = load_all_documents()
    log.info(f"  → {len(docs)} documents loaded")

    log.info("━━ Step 2: Chunking ━━")
    chunks = chunk_all(docs)
    log.info(f"  → {len(chunks)} chunks produced")

    # Stats
    by_company: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for c in chunks:
        by_company[c["company"]] = by_company.get(c["company"], 0) + 1
        by_source[c["source_type"]] = by_source.get(c["source_type"], 0) + 1
    log.info(f"  → By company: {dict(sorted(by_company.items()))}")
    log.info(f"  → By source:  {dict(sorted(by_source.items()))}")

    log.info("━━ Step 3: Building FAISS + BM25 index ━━")
    build_index(chunks)

    elapsed = time.time() - t0
    log.info(f"━━ Done in {elapsed:.1f}s — index ready at data/embeddings/ ━━")


if __name__ == "__main__":
    main()
