"""
Forum/Thread Scraper — scrapes FULL THREADS (question + ALL answers)
Targets: PrepLounge, Grapevine, igotanoffer, managementconsulted,
         datalemur, stratascratch, levels.fyi, quora, and static articles.

Core principle: a forum post without its answers has near-zero RAG value.
"""

import re
import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

import requests
import trafilatura
from bs4 import BeautifulSoup
from rich.console import Console

from scraper_config import STATIC_TARGETS, ScrapingTarget

console = Console()
log = logging.getLogger(__name__)

BASE_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

try:
    from playwright_stealth import Stealth
    _stealth = Stealth()
    HAS_STEALTH = True
except ImportError:
    _stealth = None
    HAS_STEALTH = False
    log.warning("playwright-stealth not installed — JS sites may be blocked. "
                "Run: pip install playwright-stealth")


# ──────────────────────────────────────────────────────────────
# STATIC SCRAPER (requests + trafilatura)
# ──────────────────────────────────────────────────────────────

class FullThreadScraper:

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def scrape(self, target: ScrapingTarget) -> Optional[Dict]:
        log.info(f"[forum] GET {target.url}")
        try:
            resp = self.session.get(target.url, timeout=25)
            resp.raise_for_status()
            log.debug(f"[forum] HTTP {resp.status_code} {len(resp.text)//1000}KB ← {target.url}")
        except Exception as e:
            log.error(f"[forum] HTTP FAIL — {target.name[:50]} | {e}")
            return None

        content = self._extract_by_domain(resp.text, target.url)

        if not content or len(content) < 200:
            log.warning(f"[forum] SHORT CONTENT {len(content or '')}c (min 200) — {target.name[:50]}")
            return None

        log.info(f"[forum] OK {len(content):,}c extracted — {target.name[:50]}")
        return self._make_record(target, content)

    def _extract_by_domain(self, html: str, url: str) -> str:
        domain = url.split("/")[2].lower()
        if "preplounge.com" in domain:
            method = "preplounge"
            result = self._extract_preplounge(html, url)
        elif "grapevine.in" in domain:
            method = "grapevine"
            result = self._extract_grapevine(html)
        elif "datalemur.com" in domain:
            method = "datalemur"
            result = self._extract_datalemur(html)
        elif "medium.com" in domain or "writings." in domain:
            method = "medium"
            result = self._extract_medium(html)
        else:
            method = "generic"
            result = self._extract_article_rich(html)

        log.debug(f"[forum] extractor={method} result={len(result or '')}c ← {url[-60:]}")
        return result

    # ── PrepLounge ──────────────────────────────────────────────
    def _extract_preplounge(self, html: str, url: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        parts = []

        for sel in ["h1.forum-title", "h1.question-title", "h1", "h2"]:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 5:
                parts.append(f"THREAD TITLE: {el.get_text(strip=True)}\n")
                break

        text = trafilatura.extract(html, favor_recall=True, include_comments=True, include_tables=True)
        if text and len(text) > 400:
            parts.append(text)
            return "\n".join(parts)

        soup_clean = BeautifulSoup(html, "lxml")
        for tag in soup_clean(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        seen = set()
        for block in soup_clean.find_all(
            ["div", "section", "article"],
            class_=re.compile(r"(content|body|text|answer|post|reply|comment|question|forum|thread)", re.I)
        ):
            t = block.get_text(separator="\n", strip=True)
            if len(t) > 80 and t not in seen:
                seen.add(t)
                parts.append(t)

        if not parts:
            paragraphs = [p.get_text(separator="\n", strip=True) for p in soup_clean.find_all("p")]
            parts.extend(p for p in paragraphs if len(p) > 60)

        return "\n\n".join(parts)

    # ── Grapevine ───────────────────────────────────────────────
    def _extract_grapevine(self, html: str) -> str:
        text = trafilatura.extract(html, favor_recall=True, include_comments=True)
        if text and len(text) > 300:
            return text
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        paragraphs = [p.get_text(separator="\n", strip=True) for p in soup.find_all("p")]
        return "\n\n".join(p for p in paragraphs if len(p) > 60)

    # ── DataLemur ────────────────────────────────────────────────
    def _extract_datalemur(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        parts = []
        title = soup.find("h1")
        if title:
            parts.append(f"ARTICLE: {title.get_text(strip=True)}\n")

        article = soup.find("article") or soup.find(class_=re.compile(r"(content|post|blog)", re.I))
        if article:
            for tag in article(["script", "style"]):
                tag.decompose()
            headings = article.find_all(["h2", "h3"])
            if headings:
                for h in headings:
                    parts.append(f"\n── {h.get_text(strip=True)} ──")
                    nxt = h.find_next_sibling()
                    while nxt and nxt.name not in ["h2", "h3"]:
                        t = nxt.get_text(separator="\n", strip=True)
                        if len(t) > 30:
                            parts.append(t)
                        nxt = nxt.find_next_sibling()
            else:
                parts.append(article.get_text(separator="\n", strip=True))
        else:
            text = trafilatura.extract(html, favor_recall=True, include_tables=True)
            if text:
                parts.append(text)
        return "\n".join(parts)

    # ── Medium / Blog ────────────────────────────────────────────
    def _extract_medium(self, html: str) -> str:
        return trafilatura.extract(
            html, favor_recall=True, include_comments=False, include_tables=True
        ) or ""

    # ── Generic rich article (igotanoffer, managementconsulted…) ─
    def _extract_article_rich(self, html: str) -> str:
        text = trafilatura.extract(html, favor_recall=True, include_comments=True, include_tables=True)
        if text and len(text) > 300:
            return text
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        paragraphs = [p.get_text(separator="\n", strip=True) for p in soup.find_all("p")]
        return "\n\n".join(p for p in paragraphs if len(p) > 60)

    def _make_record(self, target: ScrapingTarget, content: str) -> Dict:
        return {
            "id": hashlib.md5(target.url.encode()).hexdigest(),
            "source_name": target.name,
            "url": target.url,
            "company": target.company,
            "round_type": target.round_type,
            "source_type": target.source_type,
            "scraped_at": datetime.utcnow().isoformat(),
            "content": content,
            "char_count": len(content),
        }


# ──────────────────────────────────────────────────────────────
# PLAYWRIGHT SCRAPER (JS-heavy SPAs)
# ──────────────────────────────────────────────────────────────

class PlaywrightForumScraper:

    def scrape(self, target: ScrapingTarget) -> Optional[Dict]:
        log.info(f"[playwright] Loading: {target.url}")
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(
                    user_agent=HEADERS["User-Agent"],
                    locale="en-US",
                    viewport={"width": 1280, "height": 800},
                )
                page = ctx.new_page()
                if HAS_STEALTH:
                    _stealth.apply_stealth_sync(page)

                page.goto(target.url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                # Scroll to trigger lazy loading
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(1500)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

                self._click_expand_buttons(page)
                html = page.content()
                browser.close()

            log.debug(f"[playwright] Rendered {len(html)//1000}KB, extracting...")
            content = self._extract_rendered(html, target.url)

            if not content or len(content) < 200:
                log.warning(f"[playwright] SHORT CONTENT {len(content or '')}c — {target.name[:50]}")
                return None

            log.info(f"[playwright] OK {len(content):,}c — {target.name[:50]}")
            return {
                "id": hashlib.md5(target.url.encode()).hexdigest(),
                "source_name": target.name,
                "url": target.url,
                "company": target.company,
                "round_type": target.round_type,
                "source_type": target.source_type,
                "scraped_at": datetime.utcnow().isoformat(),
                "content": content,
                "char_count": len(content),
                "method": "playwright",
            }

        except Exception as e:
            log.error(f"[playwright] FAILED — {target.name[:50]} | {target.url} | {e}")
            return None

    def _click_expand_buttons(self, page):
        for selector in [
            "button:has-text('Load more')", "button:has-text('Show more')",
            "button:has-text('See all')", "button:has-text('Read more')",
            "a:has-text('Show more answers')", "[data-testid='load-more']",
            ".load-more", ".show-more", "[class*='loadMore']", "[class*='showMore']",
        ]:
            try:
                for btn in page.query_selector_all(selector)[:5]:
                    try:
                        btn.click()
                        page.wait_for_timeout(1000)
                    except Exception:
                        pass
            except Exception:
                pass

    def _extract_rendered(self, html: str, url: str) -> str:
        domain = url.split("/")[2].lower()

        if "preplounge.com" in domain:
            return self._extract_preplounge_rendered(html)
        if "grapevine.in" in domain:
            return self._extract_grapevine_rendered(html)
        if "quora.com" in domain:
            return self._extract_quora(html)
        if "levels.fyi" in domain:
            return self._extract_levels_fyi(html)
        if "interviewquery.com" in domain:
            return self._extract_interviewquery(html)

        text = trafilatura.extract(html, favor_recall=True, include_comments=True, include_tables=True)
        if text and len(text) > 200:
            return text
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)

    # ── PrepLounge (rendered) ────────────────────────────────────
    def _extract_preplounge_rendered(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        parts = []
        title = soup.find("h1")
        if title:
            parts.append(f"THREAD TITLE: {title.get_text(strip=True)}\n")

        text = trafilatura.extract(html, favor_recall=True, include_comments=True, include_tables=True)
        if text and len(text) > 400:
            parts.append(text)
            return "\n".join(parts)

        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        post_blocks = []
        for attr_pattern in [
            {"class": re.compile(r"(Post|Answer|Reply|Comment|Question|Thread|Forum)", re.I)},
            {"data-testid": re.compile(r"(post|answer|reply|comment)", re.I)},
        ]:
            blocks = soup.find_all(["div", "article", "section"], attrs=attr_pattern)
            if len(blocks) >= 2:
                post_blocks = blocks
                break

        if post_blocks:
            seen = set()
            for i, block in enumerate(post_blocks):
                t = block.get_text(separator="\n", strip=True)
                if len(t) > 50 and t not in seen:
                    seen.add(t)
                    label = "ORIGINAL POST" if i == 0 else f"REPLY {i}"
                    parts.append(f"── {label} ──\n{t}")
        else:
            paragraphs = [p.get_text(separator="\n", strip=True) for p in soup.find_all("p")]
            parts.extend(p for p in paragraphs if len(p) > 60)

        return "\n\n".join(parts)

    # ── Grapevine (rendered) ─────────────────────────────────────
    def _extract_grapevine_rendered(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        parts = []
        title = soup.find("h1")
        if title:
            parts.append(f"INTERVIEW EXPERIENCE: {title.get_text(strip=True)}\n")

        text = trafilatura.extract(html, favor_recall=True, include_comments=True)
        if text and len(text) > 300:
            parts.append(text)
            return "\n".join(parts)

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        for class_pat in [
            re.compile(r"(post.body|article.body|content.main)", re.I),
            re.compile(r"(comment|reply|response)", re.I),
        ]:
            for block in soup.find_all(["div", "article", "section"], class_=class_pat):
                t = block.get_text(separator="\n", strip=True)
                if len(t) > 50:
                    parts.append(t)

        if len("\n".join(parts)) < 200:
            paragraphs = [p.get_text(separator="\n", strip=True) for p in soup.find_all("p")]
            parts.extend(p for p in paragraphs if len(p) > 60)

        return "\n\n".join(parts)

    # ── Quora ────────────────────────────────────────────────────
    def _extract_quora(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        parts = []
        title = soup.find("h1")
        if title:
            parts.append(f"QUESTION: {title.get_text(strip=True)}\n")

        text = trafilatura.extract(html, favor_recall=True, include_comments=True)
        if text and len(text) > 200:
            parts.append(text)
            return "\n".join(parts)

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        seen = set()
        for block in soup.find_all(["div", "article"],
                                    class_=re.compile(r"(answer|response|post|content)", re.I)):
            t = block.get_text(separator="\n", strip=True)
            if len(t) > 100 and t not in seen:
                seen.add(t)
                parts.append(f"── ANSWER ──\n{t}")

        if not parts:
            paragraphs = [p.get_text(separator="\n", strip=True) for p in soup.find_all("p")]
            parts.extend(p for p in paragraphs if len(p) > 60)

        return "\n\n".join(parts)

    # ── Levels.fyi ───────────────────────────────────────────────
    def _extract_levels_fyi(self, html: str) -> str:
        text = trafilatura.extract(html, favor_recall=True, include_tables=True)
        if text and len(text) > 200:
            return text
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        parts = []
        for h in soup.find_all(["h2", "h3"]):
            if any(kw in h.get_text(strip=True).lower()
                   for kw in ["interview", "process", "round", "assessment"]):
                parts.append(f"\n── {h.get_text(strip=True)} ──")
                nxt = h.find_next_sibling()
                while nxt and nxt.name not in ["h2", "h3"]:
                    t = nxt.get_text(separator="\n", strip=True)
                    if len(t) > 30:
                        parts.append(t)
                    nxt = nxt.find_next_sibling()
        if not parts:
            paragraphs = [p.get_text(separator="\n", strip=True) for p in soup.find_all("p")]
            parts.extend(p for p in paragraphs if len(p) > 60)
        return "\n".join(parts)

    # ── InterviewQuery ────────────────────────────────────────────
    def _extract_interviewquery(self, html: str) -> str:
        soup = BeautifulSoup(html, "lxml")
        parts = []
        title = soup.find("h1")
        if title:
            parts.append(f"COMPANY: {title.get_text(strip=True)}\n")

        text = trafilatura.extract(html, favor_recall=True, include_tables=True)
        if text and len(text) > 200:
            parts.append(text)
            return "\n".join(parts)

        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        seen = set()
        for block in soup.find_all(
            ["div", "article"],
            class_=re.compile(r"(question|experience|interview|card|item)", re.I)
        ):
            t = block.get_text(separator="\n", strip=True)
            if len(t) > 60 and t not in seen:
                seen.add(t)
                parts.append(t)
        return "\n\n".join(parts)


# ──────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ──────────────────────────────────────────────────────────────

def run_forum_scraping():
    static = FullThreadScraper()
    playwright_scraper = PlaywrightForumScraper()
    results = {"success": 0, "failed": 0, "skipped": 0}
    total = len(STATIC_TARGETS)

    log.info(f"[forum] ── Starting forum scraping: {total} targets ──")

    for i, target in enumerate(STATIC_TARGETS, 1):
        out_dir = BASE_DATA_DIR / target.company.lower() / target.round_type.lower()
        out_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^a-z0-9_]", "_", target.name.lower())[:60]
        out_path = out_dir / f"{safe_name}.json"

        log.info(f"[forum] [{i}/{total}] {target.name[:55]}")

        if out_path.exists():
            log.debug(f"[forum] CACHED → {out_path.name}")
            results["skipped"] += 1
            continue

        record = playwright_scraper.scrape(target) if target.requires_js else static.scrape(target)

        if record:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            log.info(f"[forum] SAVED {record['char_count']:,}c → {out_path}")
            results["success"] += 1
        else:
            log.warning(f"[forum] FAILED — {target.name[:55]}")
            results["failed"] += 1

        time.sleep(1.5)

    log.info(
        f"[forum] ── Done: {results['success']} saved, "
        f"{results['failed']} failed, {results['skipped']} cached ──"
    )
    return results


if __name__ == "__main__":
    from logging_config import setup
    setup()
    run_forum_scraping()
