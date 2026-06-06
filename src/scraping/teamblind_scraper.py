"""
TeamBlind Scraper — Playwright + stealth
Searches teamblind.com and scrapes DS/analytics interview discussions for BCG/McKinsey.

Requirements:
  pip install playwright playwright-stealth
  playwright install chromium
"""

import re
import json
import time
import random
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from rich.progress import track

from scraper_config import TEAMBLIND_SEARCHES, DS_INCLUDE_KEYWORDS, DE_EXCLUDE_KEYWORDS

log = logging.getLogger(__name__)

BASE_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"
BASE_URL = "https://www.teamblind.com"
HEADERS_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "Chrome/122.0.0.0 Safari/537.36"
)

try:
    from playwright_stealth import Stealth
    _stealth = Stealth()
    HAS_STEALTH = True
except ImportError:
    _stealth = None
    HAS_STEALTH = False
    log.warning("playwright-stealth not installed — TeamBlind may block. "
                "Run: pip install playwright-stealth")


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def is_ds_relevant(title: str, body: str = "") -> bool:
    text = f"{title} {body}".lower()
    if any(kw in text for kw in DE_EXCLUDE_KEYWORDS) and \
       not any(kw in text for kw in DS_INCLUDE_KEYWORDS):
        return False
    return True


def _save_batch(batch: List[Dict], query: str, company: str, round_type: str):
    safe_q = re.sub(r"[^a-z0-9_]", "_", query.lower())[:40]
    out_dir = BASE_DATA_DIR / company.lower() / round_type.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"teamblind_{safe_q}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"query": query, "results": batch}, f, ensure_ascii=False, indent=2)
    return path


# ──────────────────────────────────────────────────────────────
# MAIN SCRAPER
# ──────────────────────────────────────────────────────────────

class TeamBlindScraper:

    def __init__(self):
        self.stats = {
            "searches": 0, "posts_found": 0,
            "posts_scraped": 0, "skipped_de": 0, "failed": 0,
        }

    def run_all_searches(self):
        log.info(f"[teamblind] ── Starting {len(TEAMBLIND_SEARCHES)} TeamBlind searches ──")
        if not HAS_STEALTH:
            log.warning("[teamblind] playwright-stealth missing — expect higher block rate")

        for cfg in track(TEAMBLIND_SEARCHES, description="TeamBlind searches..."):
            self._search_and_scrape(
                query=cfg["query"],
                company=cfg["company"],
                round_type=cfg["round_type"],
                max_posts=cfg.get("max_posts", 10),
            )
            time.sleep(random.uniform(3, 5))

        self._print_stats()

    def _search_and_scrape(
        self, query: str, company: str, round_type: str, max_posts: int = 10
    ):
        self.stats["searches"] += 1
        log.info(f"[teamblind] Search: '{query}' (max {max_posts} posts)")
        search_url = f"{BASE_URL}/search/{query.replace(' ', '%20')}"

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(
                    user_agent=HEADERS_UA,
                    locale="en-US",
                    viewport={"width": 1280, "height": 800},
                )
                page = ctx.new_page()
                if HAS_STEALTH:
                    _stealth.apply_stealth_sync(page)

                log.debug(f"[teamblind] GET search page: {search_url}")
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                for _ in range(2):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)

                post_links = self._collect_post_links(page, max_posts)
                log.info(f"[teamblind] Found {len(post_links)} posts for '{query[:50]}'")
                self.stats["posts_found"] += len(post_links)

                if not post_links:
                    log.warning(f"[teamblind] No posts found — query: '{query}'")

                batch = []
                for post_url in post_links:
                    log.info(f"[teamblind] Scraping: {post_url}")
                    record = self._scrape_post(page, post_url, company, round_type)
                    if record:
                        batch.append(record)
                        self.stats["posts_scraped"] += 1
                        log.info(f"[teamblind] Extracted {record['char_count']:,}c — {record['title'][:50]}")
                    time.sleep(random.uniform(2, 4))

                browser.close()

            if batch:
                path = _save_batch(batch, query, company, round_type)
                log.info(f"[teamblind] SAVED {len(batch)} posts → {path}")

        except Exception as e:
            log.error(f"[teamblind] Search FAILED '{query}': {e}")
            self.stats["failed"] += 1

    def _collect_post_links(self, page, max_posts: int) -> List[str]:
        links = []
        for selector in [
            "a[href*='/post/']", "a[href*='/posts/']",
            "article a", "[class*='Post'] a", "[class*='post'] a[href]",
        ]:
            try:
                elements = page.query_selector_all(selector)
                for el in elements:
                    href = el.get_attribute("href")
                    if href and "/post" in href.lower():
                        full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                        if full_url not in links:
                            links.append(full_url)
                if len(links) >= 2:
                    break
            except Exception:
                pass
        return links[:max_posts]

    def _scrape_post(
        self, page, post_url: str, company: str, round_type: str
    ) -> Optional[Dict]:
        try:
            page.goto(post_url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2500)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)

            for selector in [
                "button:has-text('Load more')", "button:has-text('See more')",
                "button:has-text('Show more')", "[class*='loadMore']",
            ]:
                try:
                    for btn in page.query_selector_all(selector)[:3]:
                        btn.click()
                        page.wait_for_timeout(1000)
                except Exception:
                    pass

            html = page.content()
            return self._parse_post_html(html, post_url, company, round_type)

        except Exception as e:
            log.error(f"[teamblind] Post FAILED {post_url}: {e}")
            self.stats["failed"] += 1
            return None

    def _parse_post_html(
        self, html: str, url: str, company: str, round_type: str
    ) -> Optional[Dict]:
        import trafilatura
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        parts = []

        title_el = soup.find("h1") or soup.find("h2")
        title = title_el.get_text(strip=True) if title_el else "TeamBlind Post"

        if not is_ds_relevant(title):
            self.stats["skipped_de"] += 1
            log.debug(f"[teamblind] SKIP off-topic: '{title[:60]}'")
            return None

        parts += [f"TITLE: {title}", f"URL: {url}", "SOURCE: TeamBlind", ""]

        # Primary: trafilatura on rendered DOM
        text = trafilatura.extract(html, favor_recall=True, include_comments=True)
        if text and len(text) > 200:
            parts += ["── CONTENT ──", text]
            content = "\n".join(parts)
            return self._make_record(title, url, company, round_type, content)

        # Fallback: BS4
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        for attr in [
            {"class": re.compile(r"(post.body|post.content|article.body)", re.I)},
            {"class": re.compile(r"(PostBody|PostContent)", re.I)},
        ]:
            body_el = soup.find(["div", "article"], attrs=attr)
            if body_el:
                t = body_el.get_text(separator="\n", strip=True)
                if len(t) > 50:
                    parts.append(f"── POST ──\n{t}")
                break

        comment_blocks = []
        for attr in [
            {"class": re.compile(r"(comment|reply|response)", re.I)},
            {"class": re.compile(r"(Comment|Reply)", re.I)},
        ]:
            blocks = soup.find_all(["div", "li"], attrs=attr)
            if blocks:
                comment_blocks = blocks
                break

        if comment_blocks:
            parts.append(f"\n── COMMENTS ({len(comment_blocks)}) ──")
            seen = set()
            for block in comment_blocks:
                t = block.get_text(separator="\n", strip=True)
                if len(t) > 20 and t not in seen:
                    seen.add(t)
                    parts.append(f"  {t}")

        if len("\n".join(parts)) < 200:
            paragraphs = [p.get_text(separator="\n", strip=True) for p in soup.find_all("p")]
            parts.extend(p for p in paragraphs if len(p) > 50)

        content = "\n".join(parts)
        if len(content) < 100:
            log.warning(f"[teamblind] Too short after extraction ({len(content)}c): {url}")
            return None

        return self._make_record(title, url, company, round_type, content)

    def _make_record(
        self, title: str, url: str, company: str, round_type: str, content: str
    ) -> Dict:
        return {
            "id": hashlib.md5(url.encode()).hexdigest(),
            "title": title,
            "url": url,
            "company": company,
            "round_type": round_type,
            "source_type": "teamblind",
            "scraped_at": datetime.utcnow().isoformat(),
            "content": content,
            "char_count": len(content),
        }

    def _print_stats(self):
        log.info(
            f"[teamblind] ── Done: {self.stats['posts_scraped']} scraped, "
            f"{self.stats['posts_found']} found, "
            f"{self.stats['skipped_de']} skipped (off-topic), "
            f"{self.stats['failed']} failed ──"
        )


if __name__ == "__main__":
    from logging_config import setup
    setup()
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=str)
    parser.add_argument("--max", type=int, default=10)
    args = parser.parse_args()

    scraper = TeamBlindScraper()
    if args.query:
        scraper._search_and_scrape(args.query, "Both", "General", max_posts=args.max)
    else:
        scraper.run_all_searches()
