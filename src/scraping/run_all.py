"""
Master entrypoint — run the full scraping pipeline.

Usage:
  python run_all.py                     # Full pipeline (Phase 1-5)
  python run_all.py --forums            # Articles + forum threads
  python run_all.py --reddit            # Reddit full threads (needs .env)
  python run_all.py --youtube           # YouTube MP4 + Whisper
  python run_all.py --teamblind         # TeamBlind discussions
  python run_all.py --glassdoor         # Glassdoor (needs .env)
  python run_all.py --glassdoor-manual FILE  # Parse manually exported HTML
  python run_all.py --check             # Show data inventory
  python run_all.py --no-whisper        # YouTube without transcription
  python run_all.py --reddit-limit 30   # Posts per Reddit search

Follow logs in real-time:
  tail -f scraping.log
"""

import argparse
import logging
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from logging_config import setup as setup_logging

console = Console()
log = logging.getLogger(__name__)


def main():
    setup_logging(log_file="scraping.log")

    parser = argparse.ArgumentParser(description="Advanced RAG — BCG/McKinsey DS Scraper")
    parser.add_argument("--forums",           action="store_true")
    parser.add_argument("--reddit",           action="store_true")
    parser.add_argument("--youtube",          action="store_true")
    parser.add_argument("--teamblind",        action="store_true")
    parser.add_argument("--glassdoor",        action="store_true")
    parser.add_argument("--check",            action="store_true")
    parser.add_argument("--no-whisper",       action="store_true")
    parser.add_argument("--reddit-limit",     type=int, default=20)
    parser.add_argument("--glassdoor-manual", type=str, default=None,
                        help="Path to manually exported Glassdoor HTML")
    args = parser.parse_args()

    run_all = not any([
        args.forums, args.reddit, args.youtube,
        args.teamblind, args.glassdoor, args.check,
    ])

    console.print(Panel.fit(
        "[bold cyan]Advanced RAG Scraper v3[/]\n"
        "BCG X (Gamma) & McKinsey QuantumBlack — Data Science / Analytics\n"
        "[dim]DS-only filter | Full threads | MP4 download | Whisper | TeamBlind[/]\n"
        "[dim]Follow logs: tail -f scraping.log[/]",
        border_style="cyan",
    ))

    if args.check:
        from data_inventory import scan_inventory
        scan_inventory()
        return

    # ── Phase 1: Forums & Articles ──────────────────────────────
    if run_all or args.forums:
        log.info("══ Phase 1: Forums & Articles ══")
        from forum_scraper import run_forum_scraping
        run_forum_scraping()

    # ── Phase 2: Reddit ─────────────────────────────────────────
    if run_all or args.reddit:
        log.info("══ Phase 2: Reddit (Full Threads) ══")
        from reddit_scraper import RedditScraper
        scraper = RedditScraper()
        scraper.run_all_searches(limit_per_search=args.reddit_limit)

    # ── Phase 3: YouTube MP4 + Whisper ──────────────────────────
    if run_all or args.youtube:
        log.info("══ Phase 3: YouTube (MP4 + Whisper) ══")
        from youtube_scraper import YouTubeScraper
        yt = YouTubeScraper(use_whisper=not args.no_whisper)
        yt.run_all_searches()

    # ── Phase 4: TeamBlind ───────────────────────────────────────
    if run_all or args.teamblind:
        log.info("══ Phase 4: TeamBlind ══")
        from teamblind_scraper import TeamBlindScraper
        tb = TeamBlindScraper()
        tb.run_all_searches()

    # ── Phase 5: Glassdoor ───────────────────────────────────────
    if run_all or args.glassdoor:
        log.info("══ Phase 5: Glassdoor ══")
        from reddit_scraper import GlassdoorScraper
        from scraper_config import GLASSDOOR_TARGETS
        import json

        gs = GlassdoorScraper()

        if args.glassdoor_manual:
            html_path = Path(args.glassdoor_manual)
            company = "BCG" if "bcg" in html_path.name.lower() else "McKinsey"
            log.info(f"[glassdoor] Parsing manual export: {html_path}")
            result = gs.parse_manual_html(html_path, company)
            if result:
                out_dir = Path(f"../../data/raw/{company.lower()}/general")
                out_dir.mkdir(parents=True, exist_ok=True)
                path = out_dir / f"glassdoor_{company.lower()}_manual_{html_path.stem}.json"
                with open(path, "w") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                log.info(f"[glassdoor] SAVED → {path}")
        else:
            for target in GLASSDOOR_TARGETS:
                log.info(f"[glassdoor] Scraping: {target['name']}")
                result = gs.scrape_with_playwright(target)
                if result:
                    out_dir = Path(f"../../data/raw/{target['company'].lower()}/general")
                    out_dir.mkdir(parents=True, exist_ok=True)
                    safe = re.sub(r"[^a-z0-9_]", "_", target["name"].lower())[:35]
                    path = out_dir / f"glassdoor_{safe}.json"
                    with open(path, "w") as f:
                        json.dump(result, f, ensure_ascii=False, indent=2)
                    log.info(f"[glassdoor] SAVED {result.get('num_reviews',0)} reviews → {path}")

    # ── Final inventory ──────────────────────────────────────────
    log.info("══ Final: Data Inventory ══")
    from data_inventory import scan_inventory
    scan_inventory()


if __name__ == "__main__":
    import re
    main()
