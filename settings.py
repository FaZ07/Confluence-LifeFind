"""
LifeFind — central configuration. Everything is env-driven with safe defaults,
so the app runs with zero configuration but can be tuned/hardened in production.
"""
from __future__ import annotations

import contextvars
import os
from pathlib import Path

APP_NAME = "LifeFind"
APP_VERSION = "2.0.0"
_HERE = Path(__file__).parent


def _b(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# --- modes -------------------------------------------------------------
ON_VERCEL = bool(os.getenv("VERCEL"))              # serverless: synchronous + no disk
# OFFLINE defaults False everywhere — Live mode is the default. The Demo/Live toggle
# in the UI overrides per-request. Set LIFELINE_OFFLINE=1 to force demo-only.
OFFLINE = _b("LIFELINE_OFFLINE", False)
SYNC = _b("LIFELINE_SYNC", False) or ON_VERCEL     # serverless MUST run inline (a bg task can't survive)
LOG_LEVEL = os.getenv("LIFELINE_LOG_LEVEL", "INFO").upper()

# Per-request data-source override (Live vs Demo). A ContextVar so the choice flows
# through the async search without leaking across concurrent cases. None -> OFFLINE default.
_OFFLINE_CTX: contextvars.ContextVar = contextvars.ContextVar("offline_ctx", default=None)


def offline_now() -> bool:
    """Effective data-source mode for the current request/case."""
    v = _OFFLINE_CTX.get()
    return OFFLINE if v is None else bool(v)


def use_offline(value: bool | None) -> None:
    """Set the per-request override (True=demo, False=live, None=use the default)."""
    _OFFLINE_CTX.set(value)

# --- outbound HTTP (hardening) -----------------------------------------
REQUEST_TIMEOUT = _f("LIFELINE_HTTP_TIMEOUT", 9.0)  # snappy live mode — never let a slow source stall the case
HTTP_RETRIES = _i("LIFELINE_HTTP_RETRIES", 1)       # extra attempts on transient errors
HTTP_BACKOFF = _f("LIFELINE_HTTP_BACKOFF", 0.5)     # seconds, exponential
MAX_LEADS_PER_SOURCE = _i("LIFELINE_MAX_LEADS_PER_SOURCE", 8)

CONTACT_EMAIL = os.getenv("LIFELINE_CONTACT", "mohamedfazil1812700@gmail.com")
USER_AGENT = f"{APP_NAME}/{APP_VERSION} (+https://github.com/FaZ07/LifeFind; {CONTACT_EMAIL})"
# Reddit 403s simple bot UAs; a real desktop-browser string gets the public JSON.
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# --- geocoding (global) ------------------------------------------------
GEOCODE_ENABLED = _b("LIFELINE_GEOCODE", True)   # gated per request by offline_now() in geo.geocode
NOMINATIM_BASE = os.getenv("LIFELINE_NOMINATIM", "https://nominatim.openstreetmap.org/search")
GEOCODE_MIN_INTERVAL = _f("LIFELINE_GEOCODE_INTERVAL", 1.1)   # OSM policy: <= 1 req/sec
GEOCODE_MAX_LOOKUPS = _i("LIFELINE_GEOCODE_MAX", 12)          # bound live lookups per case

# --- persistence -------------------------------------------------------
# Vercel/serverless filesystems are read-only except /tmp; point LIFELINE_DB there.
DB_PATH = os.getenv("LIFELINE_DB", str(_HERE / "lifefind.db"))
PERSIST = _b("LIFELINE_PERSIST", True) and not ON_VERCEL   # serverless has no writable disk
CASE_TTL_DAYS = _i("LIFELINE_CASE_TTL_DAYS", 30)
MAX_ACTIVE_CASES = _i("LIFELINE_MAX_ACTIVE_CASES", 200)   # in-memory cap; older fall back to store
GEOCODE_CACHE_MAX = _i("LIFELINE_GEOCODE_CACHE_MAX", 5000)

# --- optional LLM narration (OFF unless GROQ_API_KEY is set) -----------
# A cosmetic layer that only rephrases the deterministic engine's already-computed
# answers into clearer prose. It never changes a zone, score or decision, redacts
# the subject's identity before any call, and falls back to the deterministic text
# on any error. With no key, nothing here runs — the engine is fully self-contained.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE = os.getenv("GROQ_BASE", "https://api.groq.com/openai/v1/chat/completions")
NARRATE_TIMEOUT = _f("LIFELINE_NARRATE_TIMEOUT", 6.0)
NARRATE_OPT_IN = _b("LIFELINE_NARRATE", True)                   # operator intent (env)
NARRATE = NARRATE_OPT_IN and bool(GROQ_API_KEY)                # effective: also needs a key

# --- API hardening -----------------------------------------------------
RATE_LIMIT_PER_MIN = _i("LIFELINE_RATE_LIMIT_PER_MIN", 20)    # /api/search per client per minute
MAX_FIELD_LEN = _i("LIFELINE_MAX_FIELD_LEN", 200)
MAX_IMAGE_BYTES = _i("LIFELINE_MAX_IMAGE_BYTES", 8 * 1024 * 1024)  # photo color analysis upload cap
ALLOW_ORIGINS = [o for o in os.getenv("LIFELINE_CORS", "*").split(",") if o]
API_KEY = os.getenv("LIFELINE_API_KEY", "").strip()   # optional gate on case creation / reverse
