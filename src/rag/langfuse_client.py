"""
Langfuse singleton client + Groq auto-instrumentation.

Initialises once at import time.
No-ops gracefully if LANGFUSE_PUBLIC_KEY is not set.

What gets traced automatically after init:
  - Every Groq API call: model, messages, tokens, latency (via GroqInstrumentor)
  - @observe-decorated functions: retrieve, generate, cross_check, critique
"""

import logging
import os

from langfuse import Langfuse

log = logging.getLogger(__name__)

_client: Langfuse | None = None
_instrumented = False


def get_langfuse() -> Langfuse | None:
    """Return the global Langfuse client, or None if not configured."""
    global _client, _instrumented

    if _client is not None:
        return _client

    pub  = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    sec  = os.environ.get("LANGFUSE_SECRET_KEY", "")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")

    if not pub or not sec:
        log.debug("Langfuse not configured — tracing disabled")
        return None

    try:
        _client = Langfuse(public_key=pub, secret_key=sec, host=host)
        log.info(f"Langfuse initialised → {host}")
    except Exception as e:
        log.warning(f"Langfuse init failed (tracing disabled): {e}")
        return None

    # Auto-instrument all Groq SDK calls (tokens, latency, model captured for free)
    if not _instrumented:
        try:
            from openinference.instrumentation.groq import GroqInstrumentor
            GroqInstrumentor().instrument()
            _instrumented = True
            log.info("GroqInstrumentor active — all Groq calls are auto-traced")
        except Exception as e:
            log.warning(f"GroqInstrumentor setup failed (non-fatal): {e}")

    return _client


def flush() -> None:
    """Flush pending Langfuse events — call before process exit."""
    if _client:
        _client.flush()
