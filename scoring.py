"""
LifeLine — Deterministic lead scoring + de-duplication.

No ML, no black box. Every point on the confidence bar is explainable.
That is the whole pitch: a judge can ask "why is this lead 87?" and you read it off.

    score =  source_weight * 30      (how credible is the channel)
           + location_match * 25      (does it mention the last-seen place)
           + clothing_match * 20      (does it mention what they were wearing)
           + recency       * 15       (how fresh is the report)
           + name_match    * 10       (does it name the subject)
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import urlparse


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _contains_any(haystack: str, needles: list[str]) -> list[str]:
    """Return the needles that appear in haystack (case-insensitive)."""
    h = (haystack or "").lower()
    hits = []
    for n in needles:
        n = n.strip().lower()
        if n and n in h:
            hits.append(n)
    return hits


def _recency_score(date_str: str | None) -> float:
    """1.0 = today, decaying to ~0 over 30 days. Unknown dates -> 0.5."""
    if not date_str:
        return 0.5
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            d = datetime.strptime(date_str[: len(fmt) + 2], fmt[: len(fmt)])
            d = d.replace(tzinfo=UTC)
            age_days = (datetime.now(UTC) - d).days
            return max(0.0, 1.0 - age_days / 30.0)
        except ValueError:
            continue
    return 0.5


def score_lead(raw: dict, case: dict, source_weight: float) -> dict:
    """
    Turn a raw source result {title, snippet, url, date, ...} into a scored Lead.
    Returns the lead dict with match_score (0-100) and the attributes it matched on.
    """
    text = f"{raw.get('title', '')} {raw.get('snippet', '')}"

    child = case["child"]
    name_parts = [p for p in child.get("name", "").split() if len(p) > 1]
    location_parts = [p.strip() for p in re.split(r"[,/]", child.get("last_seen_location", "")) if p.strip()]
    clothing_parts = [p.strip() for p in re.split(r"[,]", child.get("clothing", "")) if p.strip()]

    name_hits = _contains_any(text, name_parts)
    loc_hits = _contains_any(text, location_parts)
    cloth_hits = _contains_any(text, clothing_parts)

    name_match = 1.0 if name_hits else 0.0
    location_match = min(1.0, len(loc_hits) / max(1, len(location_parts)))
    clothing_match = min(1.0, len(cloth_hits) / max(1, len(clothing_parts)))
    recency = _recency_score(raw.get("date") or raw.get("last_updated"))

    # Deterministic, explainable breakdown — a judge can ask "why 86?" and read it off.
    breakdown = {
        "source":   {"got": round(source_weight * 30),  "max": 30, "label": "Source credibility"},
        "location": {"got": round(location_match * 25),  "max": 25, "label": "Location match"},
        "clothing": {"got": round(clothing_match * 20),  "max": 20, "label": "Clothing match"},
        "recency":  {"got": round(recency * 15),         "max": 15, "label": "Recency"},
        "name":     {"got": round(name_match * 10),      "max": 10, "label": "Name match"},
    }
    score = sum(b["got"] for b in breakdown.values())  # components add up exactly

    matched = []
    if name_hits:
        matched.append(child.get("name"))
    matched += [h.title() for h in loc_hits]
    matched += [h for h in cloth_hits]

    domain = urlparse(raw.get("url", "")).netloc.replace("www.", "") or raw.get("source_name", "source")

    return {
        "id": raw.get("id") or f"{domain}-{abs(hash(raw.get('url', text))) % 100000}",
        "source_type": raw.get("source_type", "web"),
        "source_name": raw.get("source_name") or domain,
        "url": raw.get("url", ""),
        "title": raw.get("title", "(no title)"),
        "snippet": raw.get("snippet", ""),
        "date": raw.get("date") or raw.get("last_updated") or "",
        "match_score": score,
        "matched_attributes": matched,
        # A lead is on-topic only if it actually matched the subject's name,
        # last-seen location or clothing — otherwise it's generic noise.
        "on_topic": bool(matched),
        "breakdown": breakdown,
        # geo for the Operations Map
        "lat": raw.get("lat"),
        "lng": raw.get("lng"),
        "place": raw.get("place"),
        # tri-colour highlight groups for the UI
        "hl_name": name_parts,
        "hl_loc": location_parts,
        "hl_cloth": clothing_parts,
        "highlight": name_parts + location_parts + clothing_parts,  # combined fallback
        "status": "new",
    }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedup(leads: list[dict]) -> list[dict]:
    """Drop duplicates: same URL, same domain+title signature, OR the same story
    reworded across outlets (high title-token overlap). Highest score wins."""
    seen_urls: set[str] = set()
    seen_sig: set[str] = set()
    kept_tokens: list[set[str]] = []
    out: list[dict] = []
    for lead in sorted(leads, key=lambda x: x["match_score"], reverse=True):
        url = lead.get("url", "")
        domain = urlparse(url).netloc.replace("www.", "")
        toks = _tokens(lead["title"])
        sig = domain + "|" + "".join(sorted(toks))[:40]
        if url and url in seen_urls:
            continue
        if sig in seen_sig:
            continue
        if any(_jaccard(toks, kt) >= 0.7 for kt in kept_tokens):  # same story, diff outlet
            continue
        seen_urls.add(url)
        seen_sig.add(sig)
        kept_tokens.append(toks)
        out.append(lead)
    return out
