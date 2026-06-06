"""
Reddit Scraper — API JSON publique (AUCUN credential requis)
Utilise /r/{sub}/top.json au lieu de /search.json (qui retourne 403).
Filtrage des posts pertinents côté client par mots-clés.

Rate limit public Reddit : ~1 req/sec → délai 1.5s entre requêtes.
"""

import re
import json
import time
import hashlib
import logging
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

import httpx
from bs4 import BeautifulSoup
import trafilatura
from rich.progress import track

from scraper_config import (
    REDDIT_SEARCHES, REDDIT_FULL_THREADS,
    DS_INCLUDE_KEYWORDS, DE_EXCLUDE_KEYWORDS,
)

log = logging.getLogger(__name__)

BASE_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"

REDDIT_BASE = "https://www.reddit.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "Chrome/123.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def is_ds_relevant(text: str) -> bool:
    t = text.lower()
    has_de = any(kw in t for kw in DE_EXCLUDE_KEYWORDS)
    has_ds = any(kw in t for kw in DS_INCLUDE_KEYWORDS)
    if has_de and not has_ds:
        return False
    return True


def save_record(record: Dict, company: str, round_type: str, filename: str) -> Path:
    out_dir = BASE_DATA_DIR / company.lower() / round_type.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{filename}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return path


def _extract_comments(children: list, depth: int = 0) -> List[Dict]:
    """
    Extrait récursivement tous les commentaires depuis la structure JSON Reddit.
    kind=t1 → commentaire, kind=more → pagination (on skip pour simplifier).
    """
    results = []
    for item in children:
        kind = item.get("kind", "")
        if kind == "more":
            # Des commentaires supplémentaires existent mais nécessitent un appel séparé.
            # Pour le RAG, les 500 premiers commentaires sont suffisants.
            continue
        if kind != "t1":
            continue

        data = item.get("data", {})
        body = data.get("body", "")
        if not body or body in ("[deleted]", "[removed]"):
            continue

        results.append({
            "id": data.get("id", ""),
            "author": data.get("author") or "[deleted]",
            "score": data.get("score", 0),
            "depth": depth,
            "created_utc": data.get("created_utc", 0),
            "body": body,
        })

        # Réponses imbriquées
        replies = data.get("replies", {})
        if isinstance(replies, dict):
            reply_children = replies.get("data", {}).get("children", [])
            if reply_children:
                results.extend(_extract_comments(reply_children, depth + 1))

    return sorted(results, key=lambda x: -x.get("score", 0))


def format_full_thread(post: Dict, comments: List[Dict]) -> str:
    """Formate un thread complet (post + commentaires) en texte lisible pour le RAG."""
    created = datetime.fromtimestamp(post.get("created_utc", 0)).strftime("%Y-%m-%d")
    sub = post.get("subreddit", "")

    lines = [
        f"TITLE: {post.get('title', '')}",
        f"SUBREDDIT: r/{sub}",
        f"AUTHOR: u/{post.get('author', '[deleted]')}",
        f"SCORE: {post.get('score', 0)} | COMMENTS: {post.get('num_comments', 0)}",
        f"DATE: {created}",
        f"URL: https://reddit.com{post.get('permalink', '')}",
        "",
        "── ORIGINAL POST ──",
        post.get("selftext") or "[Link post — pas de texte]",
        "",
        f"── COMMENTAIRES ({len(comments)} récupérés) ──",
        "",
    ]

    for c in comments[:60]:  # cap à 60 commentaires les mieux notés
        indent = "  " * min(c["depth"], 3)
        date_str = datetime.fromtimestamp(c["created_utc"]).strftime("%Y-%m-%d")
        lines.append(f"{indent}[u/{c['author']} | ↑{c['score']} | {date_str}]")
        for body_line in c["body"].splitlines():
            lines.append(f"{indent}{body_line}")
        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# RSS HELPERS
# ──────────────────────────────────────────────────────────────

def _parse_rss_feed(xml_text: str) -> List[Dict]:
    """Parse un feed Atom Reddit (RSS) → liste de posts."""
    import xml.etree.ElementTree as ET
    import html as html_mod

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    posts = []
    for entry in root.findall("atom:entry", ns):
        raw_id = (entry.findtext("atom:id", "", ns) or "").strip()
        # Reddit IDs are like "t3_abc123" — we want just "abc123"
        post_id = raw_id.split("_")[-1] if "_" in raw_id else raw_id
        if not post_id or not raw_id.startswith("t3_"):
            continue  # Skip subreddit entries (t5_)

        link_el = entry.find("atom:link", ns)
        post_url = link_el.get("href", "") if link_el is not None else ""

        # Extract subreddit from URL
        m = re.search(r"/r/(\w+)/", post_url)
        subreddit = m.group(1) if m else ""

        title = (entry.findtext("atom:title", "", ns) or "").strip()
        author_el = entry.find("atom:author/atom:name", ns)
        raw_author = (author_el.text or "") if author_el is not None else ""
        author = re.sub(r"^/?u/", "", raw_author.strip())
        updated = entry.findtext("atom:updated", "", ns) or ""

        # Parse body from <content type="html">
        content_el = entry.find("atom:content", ns)
        body_html = content_el.text or "" if content_el is not None else ""
        body_html = html_mod.unescape(body_html)
        soup = BeautifulSoup(body_html, "lxml")
        # Remove [link] and [comments] anchors at the end
        for a in soup.find_all("a", href=True):
            if a.text in ("[link]", "[comments]"):
                a.decompose()
        body_text = soup.get_text(separator="\n").strip()

        posts.append({
            "id": post_id,
            "title": title,
            "url": post_url,
            "subreddit": subreddit,
            "author": author,
            "updated": updated,
            "selftext": body_text,
            "score": 0,        # RSS doesn't expose score
            "num_comments": 0,
        })
    return posts


# ──────────────────────────────────────────────────────────────
# REDDIT SCRAPER — RSS (no auth, no .json 403 issue)
# ──────────────────────────────────────────────────────────────

class RedditScraper:
    """
    Scrape Reddit via RSS Atom feeds — aucun credential requis.
    /search.json et /top.json retournent 403 depuis 2023 sans OAuth.
    Les feeds RSS (search.rss, top.rss) restent accessibles publiquement.

    Stratégie:
      1. search.rss?q={query}&restrict_sr=on → découverte des posts pertinents
      2. Playwright headless → rendu complet du thread (post + commentaires)
         Fallback : contenu RSS uniquement si Playwright échoue.
    """

    def __init__(self):
        self.client = httpx.Client(
            headers=HEADERS,
            follow_redirects=True,
            http2=True,
            timeout=25.0,
        )
        self.stats = {
            "posts_found": 0, "threads_scraped": 0,
            "comments_collected": 0, "skipped_de": 0, "failed": 0,
        }

    def run_all_searches(self, limit_per_search: int = 25):
        log.info(f"[reddit] ── Démarrage {len(REDDIT_SEARCHES)} recherches (RSS) ──")

        for subreddit, query, company, round_type, min_score, _sort in track(
            REDDIT_SEARCHES, description="Reddit searches..."
        ):
            self._search_and_scrape(
                subreddit=subreddit, query=query,
                company=company, round_type=round_type,
                limit=limit_per_search,
            )
            time.sleep(2)

        for url in REDDIT_FULL_THREADS:
            self._scrape_specific_thread(url)

        self.client.close()
        self._print_stats()

    def _search_and_scrape(
        self,
        subreddit: str, query: str, company: str, round_type: str,
        limit: int = 25,
    ):
        log.info(f"[reddit] r/{subreddit} | '{query[:55]}'")

        posts = self._rss_search(subreddit, query, limit)
        if not posts:
            log.warning(f"[reddit] Aucun post RSS pour r/{subreddit} '{query[:45]}'")
            return

        log.info(f"[reddit] r/{subreddit} → {len(posts)} posts RSS pour '{query[:40]}'")
        self.stats["posts_found"] += len(posts)

        batch = []
        for post in posts:
            record = self._build_thread_record(post, company, round_type)
            if record:
                batch.append(record)
                self.stats["threads_scraped"] += 1
                log.info(f"[reddit] OK {record['num_comments_scraped']}c "
                          f"| '{post['title'][:55]}'")
            time.sleep(1.5)

        if batch:
            safe_q = re.sub(r"[^a-z0-9_]", "_", query.lower())[:35]
            path = save_record(
                {"query": query, "subreddit": subreddit, "results": batch},
                company, round_type, f"reddit_{subreddit}_{safe_q}"
            )
            log.info(f"[reddit] SAVED {len(batch)} threads → {path}")
        else:
            log.warning(f"[reddit] Rien sauvegardé pour r/{subreddit} '{query[:45]}'")

    def _rss_search(self, subreddit: str, query: str, limit: int = 25) -> List[Dict]:
        """Utilise search.rss avec restrict_sr=on pour chercher dans un subreddit."""
        url = f"{REDDIT_BASE}/r/{subreddit}/search.rss"
        params = {
            "q": query, "restrict_sr": "on",
            "sort": "top", "limit": min(limit, 100),
        }

        # Company keywords that must appear in the post if present in the query
        company_terms = {"bcg", "mckinsey", "quantumblack", "gamma"}
        query_lower = query.lower()
        required_company = [t for t in company_terms if t in query_lower]

        for attempt in range(3):
            try:
                resp = self.client.get(url, params=params)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 30))
                    log.warning(f"[reddit] 429 RSS — attente {wait}s")
                    time.sleep(wait)
                    continue
                if resp.status_code in (403, 404):
                    log.warning(f"[reddit] {resp.status_code} RSS r/{subreddit} — skip")
                    return []
                if resp.status_code >= 500:
                    time.sleep(5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                posts = _parse_rss_feed(resp.text)
                relevant = []
                for p in posts:
                    text = f"{p['title']} {p['selftext']}".lower()
                    if not is_ds_relevant(text):
                        self.stats["skipped_de"] += 1
                        continue
                    # If query targets a specific company, post must mention it
                    if required_company and not any(t in text for t in required_company):
                        continue
                    relevant.append(p)
                return relevant
            except httpx.TimeoutException:
                log.warning(f"[reddit] Timeout RSS r/{subreddit} — retry {attempt+1}/3")
                time.sleep(5)
            except Exception as e:
                log.error(f"[reddit] RSS FAILED r/{subreddit} '{query}': {e}")
                self.stats["failed"] += 1
                return []
        return []

    def _build_thread_record(
        self, post: Dict, company: str, round_type: str
    ) -> Optional[Dict]:
        """
        Construit le record final.
        Essaie Playwright pour récupérer les commentaires ; fallback RSS-only.
        """
        post_id = post["id"]
        title = post["title"]
        post_url = post["url"]

        log.debug(f"[reddit] Fetching thread via Playwright: '{title[:55]}'")

        comments_text, num_comments = self._playwright_get_comments(post_url)
        self.stats["comments_collected"] += num_comments

        content = self._format_content(post, comments_text)

        return {
            "id": post_id,
            "title": title,
            "url": post_url,
            "subreddit": post.get("subreddit", ""),
            "score": post.get("score", 0),
            "num_comments": post.get("num_comments", 0),
            "num_comments_scraped": num_comments,
            "author": post.get("author", ""),
            "company": company,
            "round_type": round_type,
            "source_type": "reddit",
            "scraped_at": datetime.utcnow().isoformat(),
            "content": content,
            "char_count": len(content),
        }

    def _playwright_get_comments(self, url: str) -> tuple[str, int]:
        """
        Ouvre le thread Reddit dans Playwright et extrait les commentaires.
        Retourne (comments_text, count). Retourne ("", 0) si échec.
        """
        try:
            from playwright.sync_api import sync_playwright

            try:
                from playwright_stealth import Stealth
                _stealth_inst = Stealth()
                _has_stealth = True
            except ImportError:
                _stealth_inst = None
                _has_stealth = False

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(
                    user_agent=HEADERS["User-Agent"],
                    locale="en-US",
                    viewport={"width": 1280, "height": 900},
                )
                page = ctx.new_page()
                if _has_stealth:
                    _stealth_inst.apply_stealth_sync(page)

                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                # Scroll to load comments
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1500)

                html = page.content()
                browser.close()

            # Extract comment text
            text = trafilatura.extract(html, favor_recall=True, include_comments=True)
            if not text or len(text) < 100:
                soup = BeautifulSoup(html, "lxml")
                for tag in soup(["script", "style", "nav", "header", "footer"]):
                    tag.decompose()
                # Reddit comment selectors
                comment_els = (
                    soup.find_all(attrs={"data-testid": "comment"}) or
                    soup.find_all("div", class_=re.compile(r"-comment-", re.I)) or
                    soup.find_all("p")
                )
                texts = [el.get_text(separator="\n", strip=True)
                         for el in comment_els if len(el.get_text()) > 30]
                text = "\n\n".join(texts)

            num = text.count("\n\n") if text else 0
            return text or "", num

        except Exception as e:
            log.debug(f"[reddit] Playwright comments failed for {url}: {e}")
            return "", 0

    def _format_content(self, post: Dict, comments_text: str) -> str:
        lines = [
            f"TITLE: {post['title']}",
            f"SUBREDDIT: r/{post.get('subreddit', '')}",
            f"AUTHOR: u/{post.get('author', '')}",
            f"DATE: {post.get('updated', '')}",
            f"URL: {post['url']}",
            "",
            "── ORIGINAL POST ──",
            post.get("selftext") or "[Link post]",
        ]
        if comments_text:
            lines += ["", "── COMMENTAIRES ──", comments_text]
        return "\n".join(lines)

    def _scrape_specific_thread(self, url: str):
        """Scrape un thread Reddit par URL directe."""
        try:
            m = re.search(r"/r/(\w+)/comments/(\w+)/", url)
            if not m:
                log.error(f"[reddit] URL invalide: {url}")
                return
            subreddit, post_id = m.group(1), m.group(2)

            # Get post title from RSS top feed as a lightweight check
            fake_post = {
                "id": post_id,
                "title": url.split("/")[-2].replace("_", " ").title() if url.endswith("/") else "",
                "url": url,
                "subreddit": subreddit,
                "selftext": "",
                "author": "",
                "updated": "",
            }

            title_lower = fake_post["title"].lower()
            company = "BCG" if "bcg" in title_lower else "McKinsey" if "mckinsey" in title_lower else "Both"
            round_type = "General"
            for rt, kws in {
                "OA": ["codesignal", "online assessment"],
                "LiveCoding": ["pair programming", "tei", "coding"],
                "Case": ["case interview"],
                "PEI": ["pei", "behavioral"],
                "TakeHome": ["take home", "takehome"],
            }.items():
                if any(kw in title_lower for kw in kws):
                    round_type = rt
                    break

            record = self._build_thread_record(fake_post, company, round_type)
            if record:
                path = save_record(record, company, round_type, f"reddit_specific_{post_id}")
                log.info(f"[reddit] Thread spécifique OK → {path}")

        except Exception as e:
            log.error(f"[reddit] Thread spécifique FAILED {url}: {e}")

    def _print_stats(self):
        log.info(
            f"[reddit] ── Done: {self.stats['threads_scraped']} threads, "
            f"{self.stats['comments_collected']} commentaires, "
            f"{self.stats['posts_found']} posts trouvés, "
            f"{self.stats['skipped_de']} skippés (off-topic), "
            f"{self.stats['failed']} erreurs ──"
        )


# ──────────────────────────────────────────────────────────────
# GLASSDOOR — Playwright headless + login auto
# ──────────────────────────────────────────────────────────────

SESSION_FILE = Path(__file__).parent.parent.parent / "glassdoor_session.json"


class GlassdoorScraper:
    """
    Glassdoor scraper — session Playwright persistante.

    Workflow (une seule fois) :
        python save_glassdoor_session.py   # se connecter manuellement
    Ensuite toutes les exécutions sont automatiques (session réutilisée).

    Fallback : si pas de session → tente sans login (page 1 seulement).
    """

    # Sélecteurs pour les blocs d'avis (Glassdoor change souvent son DOM)
    _REVIEW_SELECTORS = [
        '[data-test="interview-review"]',
        '[data-test="InterviewReviewsList"] > *',
        '[class*="InterviewReview"]',
        '[class*="interview-review"]',
        'li[class*="empReview"]',
        'div[class*="gdReview"]',
        'article[class*="review"]',
        '[class*="ReviewsList"] > *',
    ]

    @staticmethod
    def _load_chrome_cookies() -> list:
        """Extrait les cookies Glassdoor depuis le profil Chrome local."""
        try:
            import browser_cookie3
            raw = browser_cookie3.chrome(domain_name=".glassdoor.com")
            cookies = []
            for c in raw:
                cookies.append({
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain or ".glassdoor.com",
                    "path": c.path or "/",
                    "httpOnly": bool(c.has_nonstandard_attr("HttpOnly")),
                    "secure": bool(c.secure),
                })
            log.info(f"[glassdoor] {len(cookies)} cookies Chrome chargés")
            return cookies
        except Exception as e:
            log.warning(f"[glassdoor] Impossible de lire les cookies Chrome: {e}")
            return []

    def scrape_with_playwright(self, target: dict) -> Optional[Dict]:
        chrome_cookies = self._load_chrome_cookies()
        has_auth = bool(chrome_cookies) or SESSION_FILE.exists()

        if not has_auth:
            log.warning(
                "[glassdoor] Aucune auth disponible. "
                "Lance: python save_glassdoor_session.py"
            )

        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import Stealth
            import shutil

            all_reviews = []
            _stealth = Stealth()

            chrome_bin = shutil.which("google-chrome") or shutil.which("chromium-browser")

            with sync_playwright() as p:
                launch_kwargs = dict(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
                if chrome_bin:
                    launch_kwargs["executable_path"] = chrome_bin

                browser = p.chromium.launch(**launch_kwargs)
                ctx_kwargs = dict(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "Chrome/123.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    viewport={"width": 1280, "height": 900},
                )
                if not chrome_cookies and SESSION_FILE.exists():
                    ctx_kwargs["storage_state"] = str(SESSION_FILE)

                ctx = browser.new_context(**ctx_kwargs)

                if chrome_cookies:
                    ctx.add_cookies(chrome_cookies)

                page = ctx.new_page()
                _stealth.apply_stealth_sync(page)

                max_pages = target["pages"] if has_auth else 1

                for page_num in range(1, max_pages + 1):
                    review_url = target["url"]
                    if page_num > 1:
                        review_url = review_url.replace(".htm", f"_P{page_num}.htm")

                    log.info(f"[glassdoor] Page {page_num}/{max_pages}: {target['name']}")
                    try:
                        page.goto(review_url, wait_until="domcontentloaded", timeout=40000)
                    except Exception as e:
                        log.warning(f"[glassdoor] Timeout page {page_num}: {e}")
                        break

                    page.wait_for_timeout(3500)

                    # Dismiss login/signup modal if it appears
                    for modal_sel in [
                        'button[alt="Close"]', '[class*="modal"] button[class*="close"]',
                        'button[data-test="dialog-close-btn"]', '[aria-label="Close"]',
                    ]:
                        try:
                            page.click(modal_sel, timeout=2000)
                            log.debug(f"[glassdoor] Modal fermé via {modal_sel}")
                            page.wait_for_timeout(500)
                        except Exception:
                            pass

                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)

                    page_reviews = self._extract_reviews_from_page(page)

                    # Fallback trafilatura si sélecteurs ratent
                    if not page_reviews:
                        html = page.content()
                        text = trafilatura.extract(html, favor_recall=True)
                        if text and len(text) > 300:
                            page_reviews = [text]
                            log.debug("[glassdoor] Fallback trafilatura utilisé")

                    all_reviews.extend(page_reviews)
                    log.info(
                        f"[glassdoor] Page {page_num}: {len(page_reviews)} avis "
                        f"(total: {len(all_reviews)})"
                    )

                    if not page_reviews:
                        log.warning(f"[glassdoor] Page vide — arrêt à la page {page_num}")
                        break

                    time.sleep(2.5)

                browser.close()

            if not all_reviews:
                log.warning(f"[glassdoor] Aucun avis extrait pour {target['name']}")
                return None

            content = (
                f"SOURCE: Glassdoor\nCOMPANY: {target['company']}\n"
                f"PAGE: {target['name']}\nROLE: Data Scientist / Analytics\n\n"
            )
            content += "\n\n─────\n\n".join(all_reviews)

            log.info(f"[glassdoor] ✓ {len(all_reviews)} avis, {len(content):,}c → {target['name']}")
            return {
                "id": hashlib.md5(target["url"].encode()).hexdigest(),
                "source_name": target["name"],
                "url": target["url"],
                "company": target["company"],
                "round_type": target["round_type"],
                "source_type": "glassdoor",
                "scraped_at": datetime.utcnow().isoformat(),
                "content": content,
                "num_reviews": len(all_reviews),
                "char_count": len(content),
            }

        except Exception as e:
            log.error(f"[glassdoor] Scrape FAILED {target['name']}: {e}")
            return None

    def _extract_reviews_from_page(self, page) -> List[str]:
        reviews = []
        seen = set()
        for selector in self._REVIEW_SELECTORS:
            try:
                blocks = page.query_selector_all(selector)
                if blocks:
                    for block in blocks:
                        try:
                            text = block.inner_text().strip()
                            if len(text) > 80 and text not in seen:
                                seen.add(text)
                                reviews.append(text)
                        except Exception:
                            pass
                    if reviews:
                        log.debug(
                            f"[glassdoor] Sélecteur OK: {selector} → {len(reviews)} blocs"
                        )
                        break
            except Exception:
                pass
        return reviews

    def parse_manual_html(self, html_path: Path, company: str) -> Optional[Dict]:
        """Parser un fichier HTML exporté manuellement depuis Glassdoor."""
        import re as _re
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "lxml")

        for tag in soup(["script", "style", "noscript", "iframe"]):
            tag.decompose()

        reviews = []
        seen = set()

        # Sélecteurs Glassdoor 2025 (vrais class names observés dans le DOM)
        selectors = [
            # Blocs d'avis individuels
            {"class": _re.compile(r"InterviewDetail_interviewDetailWrapper", _re.I)},
            {"class": _re.compile(r"InterviewDetail_contentContainer", _re.I)},
            # Résumé AI Glassdoor en haut
            {"class": _re.compile(r"EmployerSummary_description", _re.I)},
            {"class": _re.compile(r"EmployerSummary_container", _re.I)},
            # Anciens sélecteurs (fallback)
            {"data-test": "interview-review"},
            {"class": _re.compile(r"empReview|gdReview", _re.I)},
        ]

        for attrs in selectors:
            blocks = soup.find_all(["div", "li", "article"], attrs=attrs)
            for block in blocks:
                text = block.get_text(separator="\n", strip=True)
                if len(text) > 100 and text not in seen:
                    seen.add(text)
                    reviews.append(text)
            if reviews:
                log.debug(f"[glassdoor] Sélecteur {list(attrs.values())[0]} → {len(reviews)} blocs")
                break

        # Fallback trafilatura
        if not reviews:
            text = trafilatura.extract(html, favor_recall=True, include_comments=True)
            if text and len(text) > 300:
                reviews = [text]

        if not reviews:
            log.warning(f"[glassdoor] Aucun contenu trouvé dans {html_path.name}")
            return None

        content = (
            f"SOURCE: Glassdoor\nCOMPANY: {company}\n"
            f"FILE: {html_path.name}\n\n"
        ) + "\n\n─────\n\n".join(reviews)

        log.info(f"[glassdoor] Manual parse: {len(reviews)} avis, "
                 f"{len(content):,}c ← {html_path.name}")

        return {
            "id": hashlib.md5(html_path.name.encode()).hexdigest(),
            "source_name": f"Glassdoor {company} — {html_path.stem[:50]}",
            "url": "glassdoor.com (export manuel)",
            "company": company,
            "round_type": "General",
            "source_type": "glassdoor",
            "scraped_at": datetime.utcnow().isoformat(),
            "content": content,
            "num_reviews": len(reviews),
            "char_count": len(content),
        }


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from logging_config import setup
    setup()
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--reddit",           action="store_true")
    parser.add_argument("--glassdoor",        action="store_true")
    parser.add_argument("--glassdoor-manual", type=str)
    parser.add_argument("--limit",            type=int, default=25)
    args = parser.parse_args()

    if args.reddit:
        scraper = RedditScraper()
        scraper.run_all_searches(limit_per_search=args.limit)

    if args.glassdoor:
        from scraper_config import GLASSDOOR_TARGETS
        gs = GlassdoorScraper()
        for target in GLASSDOOR_TARGETS:
            result = gs.scrape_with_playwright(target)
            if result:
                out_dir = BASE_DATA_DIR / target["company"].lower() / "general"
                out_dir.mkdir(parents=True, exist_ok=True)
                path = out_dir / f"glassdoor_{target['company'].lower()}.json"
                with open(path, "w") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)

    if args.glassdoor_manual:
        from scraper_config import GLASSDOOR_TARGETS
        html_path = Path(args.glassdoor_manual)
        company = "BCG" if "bcg" in html_path.name.lower() else "McKinsey"
        gs = GlassdoorScraper()
        result = gs.parse_manual_html(html_path, company)
        if result:
            out_dir = BASE_DATA_DIR / company.lower() / "general"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"glassdoor_manual_{html_path.stem}.json"
            with open(path, "w") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
