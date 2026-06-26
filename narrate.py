"""
LifeFind — OPTIONAL narration layer (off by default).

Everything LifeFind decides — priority zones, scores, the commander's assessment —
is computed by the deterministic engine and is identical with or without this module.
When (and only when) a GROQ_API_KEY is set, this layer asks an LLM to *rephrase* an
already-computed answer into clearer, calmer prose. It is deliberately constrained:

  • it never adds a fact, number, place, time or name that wasn't already there;
  • it never changes a zone, a score or a decision;
  • it redacts the subject's identity before any network call (no name, no photo,
    no address ever leaves the box);
  • it returns the original deterministic text on any error, timeout, or when no key
    is configured — so a key being absent or Groq being down is never user-visible.

This is the honest way to use an LLM here: a cosmetic finish on top of a decision
layer that stays fully deterministic and auditable.
"""
from __future__ import annotations

import logging
import re

import httpx

import settings

log = logging.getLogger("lifefind.narrate")

_SYSTEM = (
    "You rewrite a search-operations assistant's reply in clearer, calmer, plain English "
    "for police and search teams. STRICT RULES: do not add any fact, number, place, time, "
    "or name that is not already in the text; do not speculate or give new instructions; "
    "preserve every figure exactly; keep it to 1-3 short sentences; return ONLY the "
    "rewritten reply with no preamble."
)


def enabled() -> bool:
    """True only when narration is switched on AND a key is present."""
    return bool(settings.NARRATE and settings.GROQ_API_KEY)


def status() -> dict:
    """Why narration is on/off — surfaced in /api/health for the UI status box."""
    model = settings.GROQ_MODEL
    if not settings.GROQ_API_KEY:
        return {"on": False, "model": model,
                "reason": "No GROQ_API_KEY configured. Add a key (local .env or your host's "
                          "env vars) to switch it on — the deterministic engine runs regardless."}
    if not settings.NARRATE_OPT_IN:
        return {"on": False, "model": model, "reason": "Turned off via LIFELINE_NARRATE=0."}
    return {"on": True, "model": model, "reason": "Active — polishing the commander chat replies."}


def _redact(text: str, child: dict | None) -> str:
    """Replace the subject's name (full and token-wise) with a neutral label so no
    identifying detail is sent to the LLM. Best-effort; the payload is built only
    from the deterministic answer, never from the photo or raw profile."""
    if not child:
        return text
    out = text
    name = (child.get("name") or "").strip()
    tokens = [name] + [t for t in name.split() if len(t) >= 3]
    for tok in sorted(set(tokens), key=len, reverse=True):
        if len(tok) >= 3:
            out = re.sub(re.escape(tok), "the subject", out, flags=re.IGNORECASE)
    return out


async def polish(text: str, *, child: dict | None = None) -> str:
    """Return a nicer rephrasing of `text`, or `text` unchanged if disabled or anything
    fails. Redacts the subject's identity before sending; never sends photos or PII."""
    if not enabled() or not text or len(text) > 1200:
        return text
    safe = _redact(text, child)
    try:
        async with httpx.AsyncClient(timeout=settings.NARRATE_TIMEOUT) as client:
            r = await client.post(
                settings.GROQ_BASE,
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                json={
                    "model": settings.GROQ_MODEL,
                    "temperature": 0.2,
                    "max_tokens": 220,
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": safe},
                    ],
                },
            )
            r.raise_for_status()
            out = (r.json()["choices"][0]["message"]["content"] or "").strip()
            return out or text
    except Exception as e:  # noqa: BLE001 — optional layer: always fall back to deterministic text
        log.info("narrate fallback (%s): %s", type(e).__name__, e)
        return text
