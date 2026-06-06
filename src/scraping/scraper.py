"""
Core scraper module — advanced-rag project
Strategies:
  1. Static HTTP  → requests + trafilatura  (fast, no JS)
  2. Reddit JSON  → reddit pushshift/json API (no auth needed)
  3. YouTube      → yt-dlp subtitles/transcripts
  4. Playwright   → JS-heavy pages (glassdoor, medium, teamblind)

Output: structured JSON files per source → data/raw/<company>/<round_type>/
"""

import os
import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import asdict

import requests
import trafilatura
from rich.console import Console
from rich.progress import track
from rich.panel import Panel
from rich.table import Table

from scraper_config import SCRAPING_TARGETS, REDDIT_SEARCHES, YOUTUBE_VIDEO_TARGETS, ScrapingTarget

# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraping.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

BASE_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ─────────────────────────────────────────────
# UTILS
# ─────────────────────────────────────────────

def get_output_path(company: str, round_type: str, source_name: str, ext: str = "json") -> Path:
    """Build canonical output path for scraped data."""
    company_dir = BASE_DATA_DIR / company.lower() / round_type.lower()
    company_dir.mkdir(parents=True, exist_ok=True)
    slug = hashlib.md5(source_name.encode()).hexdigest()[:8]
    safe_name = source_name[:60].replace("/", "_").replace(" ", "_").lower()
    return company_dir / f"{safe_name}_{slug}.{ext}"


def save_result(data: Dict[str, Any], path: Path) -> None:
    """Save scraped result to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log.info(f"Saved → {path}")


def already_scraped(path: Path) -> bool:
    """Skip if we already have fresh data (< 7 days old)."""
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < 7 * 86400  # 7 days


def make_record(target: ScrapingTarget, content: str, extra: Dict = None) -> Dict:
    """Standard record structure for RAG ingestion."""
    return {
        "id": hashlib.md5(target.url.encode()).hexdigest(),
        "source_name": target.name,
        "url": target.url,
        "company": target.company,
        "round_type": target.round_type,
        "source_type": target.source_type,
        "scraped_at": datetime.utcnow().isoformat(),
        "content": content,
        "notes": target.notes,
        **(extra or {}),
    }


# ─────────────────────────────────────────────
# STRATEGY 1: STATIC HTTP SCRAPER
# ─────────────────────────────────────────────

class StaticScraper:
    """Uses requests + trafilatura for clean text extraction."""

    def __init__(self, delay: float = 1.5):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.delay = delay

    def scrape(self, target: ScrapingTarget) -> Optional[Dict]:
        try:
            resp = self.session.get(target.url, timeout=20)
            resp.raise_for_status()
            time.sleep(self.delay)

            # trafilatura: best-in-class article extraction
            text = trafilatura.extract(
                resp.text,
                include_comments=True,
                include_tables=True,
                favor_recall=True,
            )
            if not text or len(text) < 200:
                log.warning(f"Short content ({len(text or '')} chars) for {target.name}")
                return None

            return make_record(target, text, {"char_count": len(text), "status_code": resp.status_code})

        except Exception as e:
            log.error(f"StaticScraper failed for {target.url}: {e}")
            return None


# ─────────────────────────────────────────────
# STRATEGY 2: REDDIT JSON API
# ─────────────────────────────────────────────

class RedditScraper:
    """
    Uses Reddit's public JSON API (no auth).
    GET https://www.reddit.com/r/{sub}/search.json?q=...&sort=top&limit=25
    """

    BASE = "https://www.reddit.com"
    HEADERS = {**HEADERS, "User-Agent": "advanced-rag-scraper/1.0 (research project)"}

    def __init__(self, delay: float = 2.0):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.delay = delay

    def search_subreddit(
        self,
        subreddit: str,
        query: str,
        company: str,
        round_type: str,
        limit: int = 25,
        time_filter: str = "all",
    ) -> List[Dict]:
        """Search a subreddit and return post + top comments."""
        results = []
        url = f"{self.BASE}/r/{subreddit}/search.json"
        params = {
            "q": query,
            "sort": "top",
            "limit": limit,
            "t": time_filter,
            "restrict_sr": "true",
        }

        try:
            resp = self.session.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            posts = data.get("data", {}).get("children", [])

            console.print(f"  [cyan]r/{subreddit}[/] — '{query}' → {len(posts)} posts")

            for post in posts:
                pd = post.get("data", {})
                if pd.get("score", 0) < 5:
                    continue

                post_content = self._format_post(pd)
                comments = self._fetch_top_comments(pd.get("permalink", ""))
                full_content = post_content + "\n\n--- TOP COMMENTS ---\n\n" + comments

                results.append({
                    "id": pd.get("id"),
                    "url": f"{self.BASE}{pd.get('permalink')}",
                    "title": pd.get("title"),
                    "score": pd.get("score"),
                    "num_comments": pd.get("num_comments"),
                    "created_utc": pd.get("created_utc"),
                    "subreddit": subreddit,
                    "query": query,
                    "company": company,
                    "round_type": round_type,
                    "source_type": "reddit",
                    "scraped_at": datetime.utcnow().isoformat(),
                    "content": full_content,
                })
                time.sleep(self.delay)

        except Exception as e:
            log.error(f"Reddit search failed r/{subreddit} q='{query}': {e}")

        return results

    def _format_post(self, post_data: Dict) -> str:
        title = post_data.get("title", "")
        selftext = post_data.get("selftext", "")
        author = post_data.get("author", "")
        score = post_data.get("score", 0)
        created = datetime.fromtimestamp(post_data.get("created_utc", 0)).strftime("%Y-%m-%d")
        return f"TITLE: {title}\nAUTHOR: u/{author}\nSCORE: {score}\nDATE: {created}\n\nPOST:\n{selftext}"

    def _fetch_top_comments(self, permalink: str, top_n: int = 10) -> str:
        """Fetch top-level comments from a post."""
        if not permalink:
            return ""
        try:
            url = f"{self.BASE}{permalink}.json?sort=top&limit={top_n}"
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            if len(data) < 2:
                return ""

            comments_data = data[1].get("data", {}).get("children", [])
            comments = []
            for c in comments_data[:top_n]:
                cd = c.get("data", {})
                if cd.get("body") and cd.get("score", 0) > 2:
                    comments.append(
                        f"[u/{cd.get('author')} | score:{cd.get('score')}]\n{cd.get('body')}"
                    )
            time.sleep(1.0)
            return "\n\n---\n\n".join(comments)

        except Exception as e:
            log.warning(f"Comment fetch failed {permalink}: {e}")
            return ""

    def scrape_url(self, target: ScrapingTarget) -> Optional[Dict]:
        """Fallback: scrape a specific reddit URL as static."""
        json_url = target.url.rstrip("/") + ".json?sort=top&limit=25"
        try:
            resp = self.session.get(json_url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            text = trafilatura.extract(resp.text, favor_recall=True) or str(data)[:5000]
            return make_record(target, text)
        except Exception as e:
            log.error(f"Reddit URL scrape failed {target.url}: {e}")
            return None


# ─────────────────────────────────────────────
# STRATEGY 3: YOUTUBE TRANSCRIPT EXTRACTOR
# ─────────────────────────────────────────────

class YouTubeScraper:
    """
    Uses yt-dlp to search YouTube and extract subtitles/transcripts.
    Falls back to video description + metadata if no subtitles.
    """

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or (BASE_DATA_DIR / "_youtube_tmp")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def search_and_extract(
        self,
        query: str,
        company: str,
        round_type: str,
        max_results: int = 5,
    ) -> List[Dict]:
        """Search YouTube and extract transcripts for top results."""
        import subprocess
        results = []

        search_url = f"ytsearch{max_results}:{query}"
        tmp_out = self.output_dir / f"%(id)s"

        cmd = [
            "yt-dlp",
            "--write-auto-sub",
            "--write-sub",
            "--sub-lang", "en",
            "--sub-format", "vtt",
            "--skip-download",
            "--write-info-json",
            "--no-playlist",
            "--output", str(tmp_out),
            "--quiet",
            "--no-warnings",
            search_url,
        ]

        console.print(f"  [yellow]YouTube[/] searching: '{query}'")
        try:
            subprocess.run(cmd, timeout=120, check=False, capture_output=True)
        except Exception as e:
            log.error(f"yt-dlp failed: {e}")
            return results

        # Parse downloaded info JSONs
        for info_file in self.output_dir.glob("*.info.json"):
            try:
                with open(info_file) as f:
                    info = json.load(f)

                video_id = info.get("id", "")
                title = info.get("title", "")
                description = info.get("description", "")[:2000]
                duration = info.get("duration", 0)
                view_count = info.get("view_count", 0)
                upload_date = info.get("upload_date", "")
                url = f"https://www.youtube.com/watch?v={video_id}"

                # Try to read subtitle file
                transcript = ""
                for sub_file in self.output_dir.glob(f"{video_id}*.vtt"):
                    transcript = self._parse_vtt(sub_file)
                    sub_file.unlink(missing_ok=True)
                    break

                content = f"TITLE: {title}\n"
                content += f"URL: {url}\n"
                content += f"DURATION: {duration}s | VIEWS: {view_count} | DATE: {upload_date}\n\n"
                content += f"DESCRIPTION:\n{description}\n\n"
                if transcript:
                    content += f"TRANSCRIPT:\n{transcript}"

                results.append({
                    "id": video_id,
                    "url": url,
                    "title": title,
                    "duration_seconds": duration,
                    "view_count": view_count,
                    "upload_date": upload_date,
                    "company": company,
                    "round_type": round_type,
                    "source_type": "youtube",
                    "search_query": query,
                    "has_transcript": bool(transcript),
                    "scraped_at": datetime.utcnow().isoformat(),
                    "content": content,
                })
                info_file.unlink(missing_ok=True)

            except Exception as e:
                log.warning(f"Failed to parse info JSON {info_file}: {e}")

        console.print(f"  [green]YouTube[/] extracted {len(results)} videos for '{query}'")
        return results

    def _parse_vtt(self, vtt_path: Path) -> str:
        """Parse WebVTT subtitle file into clean text."""
        lines = vtt_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        seen = set()
        text_lines = []
        for line in lines:
            line = line.strip()
            if not line or "-->" in line or line.startswith("WEBVTT") or line.isdigit():
                continue
            # Remove HTML tags
            import re
            line = re.sub(r"<[^>]+>", "", line)
            if line and line not in seen:
                seen.add(line)
                text_lines.append(line)
        return " ".join(text_lines)


# ─────────────────────────────────────────────
# STRATEGY 4: PLAYWRIGHT (JS-heavy sites)
# ─────────────────────────────────────────────

class PlaywrightScraper:
    """
    Headless browser for JS-rendered pages (Glassdoor, Medium, Blind, etc.)
    Install: playwright install chromium
    """

    def scrape(self, target: ScrapingTarget, wait_selector: str = "body") -> Optional[Dict]:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=HEADERS["User-Agent"],
                    locale="en-US",
                )
                page = context.new_page()
                page.goto(target.url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                html = page.content()
                browser.close()

            text = trafilatura.extract(html, favor_recall=True, include_comments=True)
            if not text or len(text) < 100:
                log.warning(f"Playwright: short content for {target.name}")
                return None

            return make_record(target, text, {"method": "playwright"})

        except Exception as e:
            log.error(f"Playwright failed for {target.url}: {e}")
            return None


# ─────────────────────────────────────────────
# MASTER ORCHESTRATOR
# ─────────────────────────────────────────────

class ScrapingOrchestrator:

    def __init__(self, dry_run: bool = False, skip_js: bool = False):
        self.dry_run = dry_run
        self.skip_js = skip_js
        self.static = StaticScraper()
        self.reddit = RedditScraper()
        self.youtube = YouTubeScraper()
        self.playwright = PlaywrightScraper()
        self.stats = {"success": 0, "skipped": 0, "failed": 0, "total": 0}

    def run_all(self):
        console.print(Panel.fit(
            "[bold cyan]Advanced RAG Scraper[/]\n"
            "BCG X & McKinsey Data Science Recruitment",
            border_style="cyan"
        ))

        # ── Phase 1: Static articles ──────────────────
        console.print("\n[bold]Phase 1: Static Articles & Blogs[/]")
        static_targets = [t for t in SCRAPING_TARGETS if not t.requires_js and t.source_type != "reddit" and t.source_type != "youtube"]
        for target in track(static_targets, description="Scraping articles..."):
            self._scrape_target(target, strategy="static")

        # ── Phase 2: Reddit API ───────────────────────
        console.print("\n[bold]Phase 2: Reddit JSON API[/]")
        self._run_reddit_searches()

        # ── Phase 3: YouTube Transcripts ─────────────
        console.print("\n[bold]Phase 3: YouTube Transcripts[/]")
        self._run_youtube_searches()

        # ── Phase 4: JS-heavy (Playwright) ───────────
        if not self.skip_js:
            console.print("\n[bold]Phase 4: JS-Heavy Sites (Playwright)[/]")
            js_targets = [t for t in SCRAPING_TARGETS if t.requires_js and not t.requires_auth and t.source_type != "reddit"]
            for target in track(js_targets, description="Playwright scraping..."):
                self._scrape_target(target, strategy="playwright")
        else:
            console.print("[yellow]Skipping JS-heavy sites (--skip-js flag)[/]")

        # ── Summary ───────────────────────────────────
        self._print_summary()

    def _scrape_target(self, target: ScrapingTarget, strategy: str = "auto"):
        self.stats["total"] += 1
        out_path = get_output_path(target.company, target.round_type, target.name)

        if already_scraped(out_path):
            console.print(f"  [dim]SKIP (cached)[/] {target.name[:60]}")
            self.stats["skipped"] += 1
            return

        if self.dry_run:
            console.print(f"  [blue]DRY RUN[/] {target.name[:60]}")
            return

        result = None
        if strategy == "static":
            result = self.static.scrape(target)
        elif strategy == "playwright":
            result = self.playwright.scrape(target)
        elif strategy == "reddit":
            result = self.reddit.scrape_url(target)
        else:
            result = (self.playwright if target.requires_js else self.static).scrape(target)

        if result:
            save_result(result, out_path)
            self.stats["success"] += 1
            console.print(f"  [green]OK[/] {target.name[:60]} ({result.get('char_count', '?')} chars)")
        else:
            self.stats["failed"] += 1
            console.print(f"  [red]FAIL[/] {target.name[:60]}")

    def _run_reddit_searches(self):
        all_results = []
        for subreddit, query, company, round_type in REDDIT_SEARCHES:
            results = self.reddit.search_subreddit(subreddit, query, company, round_type)
            all_results.extend(results)

            # Save per search
            if results:
                out_path = get_output_path(
                    company, round_type, f"reddit_{subreddit}_{query[:30]}"
                )
                if not already_scraped(out_path):
                    save_result({"results": results, "query": query, "subreddit": subreddit}, out_path)
                    self.stats["success"] += 1

        console.print(f"  [green]Reddit total:[/] {len(all_results)} posts collected")

    def _run_youtube_searches(self):
        for target in YOUTUBE_VIDEO_TARGETS:
            query = target["id"].replace("search:", "")
            results = self.youtube.search_and_extract(
                query=query,
                company=target["company"],
                round_type=target["round_type"],
                max_results=target.get("max_results", 3),
            )
            if results:
                out_path = get_output_path(
                    target["company"], target["round_type"], f"youtube_{query[:40]}"
                )
                save_result({"results": results, "query": query}, out_path)
                self.stats["success"] += 1

    def _print_summary(self):
        table = Table(title="Scraping Summary", border_style="cyan")
        table.add_column("Metric", style="bold")
        table.add_column("Count", style="cyan")
        table.add_row("Total targets", str(self.stats["total"]))
        table.add_row("[green]Success[/]", str(self.stats["success"]))
        table.add_row("[yellow]Skipped (cached)[/]", str(self.stats["skipped"]))
        table.add_row("[red]Failed[/]", str(self.stats["failed"]))
        console.print(table)

        # List all output files
        all_files = list(BASE_DATA_DIR.rglob("*.json"))
        console.print(f"\n[bold]Total files in data/raw:[/] {len(all_files)}")


# ─────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BCG/McKinsey RAG Data Scraper")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be scraped, don't execute")
    parser.add_argument("--skip-js", action="store_true", help="Skip Playwright JS-heavy sites")
    parser.add_argument("--only", choices=["static", "reddit", "youtube", "playwright"], help="Run only one strategy")
    parser.add_argument("--company", choices=["BCG", "McKinsey", "Both"], help="Filter by company")
    args = parser.parse_args()

    orch = ScrapingOrchestrator(dry_run=args.dry_run, skip_js=args.skip_js)

    if args.only == "static":
        targets = [t for t in SCRAPING_TARGETS if not t.requires_js]
        for t in targets:
            orch._scrape_target(t, strategy="static")
    elif args.only == "reddit":
        orch._run_reddit_searches()
    elif args.only == "youtube":
        orch._run_youtube_searches()
    elif args.only == "playwright":
        targets = [t for t in SCRAPING_TARGETS if t.requires_js]
        for t in targets:
            orch._scrape_target(t, strategy="playwright")
    else:
        orch.run_all()