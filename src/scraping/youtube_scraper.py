"""
YouTube Scraper — yt-dlp + Whisper (local transcription)
Downloads full MP4 videos, transcribes with Whisper, stores JSON for RAG.

Requirements:
  pip install yt-dlp openai-whisper torch
  ffmpeg (system): sudo apt install ffmpeg
"""

import json
import subprocess
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from rich.progress import track

from scraper_config import (
    YOUTUBE_SEARCHES, YOUTUBE_MAX_DURATION_SECONDS, WHISPER_MODEL,
    DE_EXCLUDE_KEYWORDS,
)

log = logging.getLogger(__name__)

BASE_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"
VIDEO_DIR = BASE_DATA_DIR / "_youtube_videos"
AUDIO_TMP_DIR = BASE_DATA_DIR / "_youtube_audio_tmp"

VIDEO_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_TMP_DIR.mkdir(parents=True, exist_ok=True)


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def is_ds_relevant_video(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    de_terms = DE_EXCLUDE_KEYWORDS + ["devops", "backend engineer", "platform engineer",
                                       "data infrastructure", "etl pipeline"]
    if any(t in text for t in de_terms):
        return False
    ds_terms = ["data scientist", "data science", "analytics", "data analyst",
                 "machine learning", "bcg", "mckinsey", "quantumblack",
                 "codesignal", "pair programming", "case interview", "take home",
                 "pei", "tei", "behavioral", "ml engineer", "statistical",
                 "python interview", "consulting interview", "oa assessment",
                 "analytics consultant", "quantitative analyst"]
    return any(t in text for t in ds_terms)


def clean_transcript(raw_text: str) -> str:
    """Remove Whisper hallucination repetitions."""
    lines = raw_text.splitlines()
    seen = set()
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            clean_lines.append(stripped)
    return " ".join(clean_lines)


# ──────────────────────────────────────────────────────────────
# YOUTUBE SCRAPER
# ──────────────────────────────────────────────────────────────

class YouTubeScraper:

    def __init__(self, use_whisper: bool = True):
        self.use_whisper = use_whisper
        self._whisper_model = None
        self.stats = {
            "searched": 0, "downloaded": 0, "transcribed": 0,
            "skipped_de": 0, "skipped_long": 0, "failed": 0,
        }

    def _load_whisper(self):
        if self._whisper_model is None:
            log.info(f"[whisper] Loading model '{WHISPER_MODEL}'...")
            import whisper
            self._whisper_model = whisper.load_model(WHISPER_MODEL)
            log.info(f"[whisper] Model loaded: {WHISPER_MODEL}")
        return self._whisper_model

    def run_all_searches(self):
        log.info(f"[youtube] ── Starting {len(YOUTUBE_SEARCHES)} YouTube searches ──")

        for search_cfg in track(YOUTUBE_SEARCHES, description="YouTube searches..."):
            results = self._search_and_process(
                query=search_cfg["query"],
                company=search_cfg["company"],
                round_type=search_cfg["round_type"],
                max_results=search_cfg["max"],
            )
            if results:
                safe_q = re.sub(r"[^a-z0-9_]", "_", search_cfg["query"].lower())[:40]
                out_dir = BASE_DATA_DIR / search_cfg["company"].lower() / search_cfg["round_type"].lower()
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"youtube_{safe_q}.json"
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump({"query": search_cfg["query"], "results": results}, f,
                              ensure_ascii=False, indent=2)
                log.info(f"[youtube] SAVED {len(results)} videos → {out_path}")

        self._print_stats()

    def _search_and_process(
        self, query: str, company: str, round_type: str, max_results: int = 5
    ) -> List[Dict]:
        self.stats["searched"] += 1
        log.info(f"[youtube] Search: '{query}'")

        video_infos = self._yt_search_metadata(query, max_results * 3)
        log.info(f"[youtube] {len(video_infos)} candidates for '{query[:50]}'")

        results = []
        processed = 0

        for info in video_infos:
            if processed >= max_results:
                break

            title = info.get("title", "")
            description = (info.get("description") or "")[:500]
            duration = info.get("duration") or 0
            video_id = info.get("id", "")

            if not video_id:
                continue

            if not is_ds_relevant_video(title, description):
                self.stats["skipped_de"] += 1
                log.debug(f"[youtube] SKIP off-topic: '{title[:60]}'")
                continue

            if duration > YOUTUBE_MAX_DURATION_SECONDS:
                self.stats["skipped_long"] += 1
                log.warning(f"[youtube] SKIP too long ({duration//60}min): '{title[:60]}'")
                continue

            log.info(f"[youtube] Processing: '{title[:55]}' | {duration//60}min | {video_id}")

            video_path = self._download_video(video_id)
            if not video_path:
                self.stats["failed"] += 1
                continue

            self.stats["downloaded"] += 1

            transcript = ""
            if self.use_whisper:
                transcript = self._transcribe_whisper(video_path)
                if transcript:
                    self.stats["transcribed"] += 1

            content = self._build_content(info, transcript, video_path)
            results.append({
                "id": video_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "channel": info.get("uploader") or info.get("channel", ""),
                "duration_seconds": duration,
                "view_count": info.get("view_count", 0),
                "upload_date": info.get("upload_date", ""),
                "company": company,
                "round_type": round_type,
                "source_type": "youtube",
                "search_query": query,
                "has_transcript": bool(transcript),
                "whisper_model": WHISPER_MODEL if transcript else None,
                "video_path": str(video_path) if video_path else None,
                "scraped_at": datetime.utcnow().isoformat(),
                "content": content,
                "char_count": len(content),
            })
            processed += 1

        log.info(f"[youtube] Search done: {processed} videos processed for '{query[:50]}'")
        return results

    def _yt_search_metadata(self, query: str, limit: int) -> List[Dict]:
        cmd = [
            "yt-dlp", "--flat-playlist", "--print-json",
            "--no-warnings", "--quiet", f"ytsearch{limit}:{query}",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            infos = []
            for line in result.stdout.strip().splitlines():
                if line.strip():
                    try:
                        infos.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            if result.returncode != 0 and result.stderr:
                log.debug(f"[youtube] yt-dlp stderr: {result.stderr[:200]}")
            return infos
        except subprocess.TimeoutExpired:
            log.error(f"[youtube] yt-dlp metadata timeout for: '{query}'")
            return []
        except Exception as e:
            log.error(f"[youtube] yt-dlp metadata failed for '{query}': {e}")
            return []

    def _download_video(self, video_id: str) -> Optional[Path]:
        existing = VIDEO_DIR / f"{video_id}.mp4"
        if existing.exists():
            log.debug(f"[youtube] Cached MP4: {video_id} ({existing.stat().st_size//1024//1024}MB)")
            return existing

        log.info(f"[youtube] Downloading MP4: https://youtu.be/{video_id}")
        output_template = str(VIDEO_DIR / f"{video_id}.%(ext)s")
        cmd = [
            "yt-dlp",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--no-playlist", "--quiet", "--no-warnings",
            "-o", output_template,
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        try:
            proc = subprocess.run(cmd, timeout=300, check=False, capture_output=True)
            if proc.returncode != 0:
                log.warning(f"[youtube] yt-dlp exit {proc.returncode} for {video_id}: "
                             f"{proc.stderr.decode()[:200]}")

            mp4_path = VIDEO_DIR / f"{video_id}.mp4"
            if mp4_path.exists():
                size_mb = mp4_path.stat().st_size / (1024 * 1024)
                log.info(f"[youtube] Downloaded {size_mb:.1f}MB → {mp4_path.name}")
                return mp4_path

            for ext in ["mkv", "webm", "mov"]:
                alt = VIDEO_DIR / f"{video_id}.{ext}"
                if alt.exists():
                    size_mb = alt.stat().st_size / (1024 * 1024)
                    log.info(f"[youtube] Downloaded {size_mb:.1f}MB (.{ext}) → {alt.name}")
                    return alt

            log.error(f"[youtube] Download FAILED — no file found for {video_id}")
            return None

        except subprocess.TimeoutExpired:
            log.error(f"[youtube] Download TIMEOUT (>5min): {video_id}")
            return None
        except Exception as e:
            log.error(f"[youtube] Download EXCEPTION {video_id}: {e}")
            return None

    def _transcribe_whisper(self, video_path: Path) -> str:
        log.info(f"[whisper] Transcribing: {video_path.name} "
                  f"({video_path.stat().st_size//1024//1024}MB)")
        try:
            model = self._load_whisper()
            result = model.transcribe(
                str(video_path),
                language="en",
                task="transcribe",
                fp16=False,
                verbose=False,
            )
            raw = result.get("text", "")
            cleaned = clean_transcript(raw)
            log.info(f"[whisper] Done: {len(cleaned):,} chars ← {video_path.name}")
            return cleaned
        except Exception as e:
            log.error(f"[whisper] FAILED {video_path.name}: {e}")
            return ""

    def _build_content(self, info: Dict, transcript: str, video_path: Optional[Path]) -> str:
        video_id = info.get("id", "")
        title = info.get("title", "")
        channel = info.get("uploader") or info.get("channel", "")
        duration = info.get("duration") or 0
        views = info.get("view_count", 0)
        date = info.get("upload_date", "")
        description = (info.get("description") or "")[:1000]

        lines = [
            "SOURCE: YouTube",
            f"TITLE: {title}",
            f"CHANNEL: {channel}",
            f"URL: https://www.youtube.com/watch?v={video_id}",
            f"DURATION: {duration//60}min {duration%60}s | VIEWS: {views:,} | DATE: {date}",
        ]
        if video_path:
            lines.append(f"VIDEO_FILE: {video_path}")
        lines.append("")
        if description:
            lines += ["── DESCRIPTION ──", description, ""]
        if transcript:
            lines += ["── TRANSCRIPT (Whisper) ──", transcript]
        else:
            lines += ["[No transcript available]"]
        return "\n".join(lines)

    def _print_stats(self):
        log.info(
            f"[youtube] ── Done: {self.stats['downloaded']} downloaded, "
            f"{self.stats['transcribed']} transcribed, "
            f"{self.stats['skipped_de']} skipped (off-topic), "
            f"{self.stats['skipped_long']} skipped (too long), "
            f"{self.stats['failed']} failed ──"
        )
        log.info(f"[youtube] Videos stored in: {VIDEO_DIR.resolve()}")


if __name__ == "__main__":
    from logging_config import setup
    setup()
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-whisper", action="store_true")
    parser.add_argument("--video-id", type=str)
    parser.add_argument("--query", type=str)
    parser.add_argument("--max", type=int, default=3)
    args = parser.parse_args()

    scraper = YouTubeScraper(use_whisper=not args.no_whisper)
    if args.video_id:
        path = scraper._download_video(args.video_id)
        if path and not args.no_whisper:
            t = scraper._transcribe_whisper(path)
            print(t[:2000])
    elif args.query:
        r = scraper._search_and_process(args.query, "Both", "General", max_results=args.max)
        log.info(f"Got {len(r)} results")
    else:
        scraper.run_all_searches()
