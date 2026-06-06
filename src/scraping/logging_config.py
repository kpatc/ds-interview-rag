"""
Centralized logging setup for the scraping pipeline.

Console  → RichHandler  (colors, icons, realtime)
File     → scraping.log (plain text, tail -f friendly)

Usage in every module:
    from logging_config import get_logger
    log = get_logger(__name__)

Or at program entry:
    from logging_config import setup
    setup()
"""

import logging
import sys
from datetime import datetime
from pathlib import Path


_CONFIGURED = False


def setup(log_file: str = "scraping.log", level: int = logging.INFO) -> None:
    """
    Configure root logger once. Safe to call multiple times.
    File handler captures DEBUG+, console captures INFO+.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # ── File handler (DEBUG level — captures everything) ───────
    fh = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)-22s] %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(fh)

    # ── Console handler ─────────────────────────────────────────
    try:
        from rich.logging import RichHandler
        ch = RichHandler(
            level=level,
            rich_tracebacks=True,
            tracebacks_show_locals=False,
            markup=True,
            show_path=False,
            log_time_format="[%H:%M:%S]",
        )
    except ImportError:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        ch.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
    root.addHandler(ch)

    # Silence noisy third-party libraries
    for lib in ["urllib3", "httpx", "asyncio", "PIL", "filelock",
                 "httpcore", "hpack", "charset_normalizer"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

    # ── Session header in log file ──────────────────────────────
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n{'═' * 60}\n")
        f.write(f"  SESSION: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'═' * 60}\n\n")

    logging.getLogger(__name__).info(
        f"Logging to [bold]{Path(log_file).resolve()}[/bold]  (tail -f to follow)"
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. setup() must have been called first."""
    return logging.getLogger(name)
