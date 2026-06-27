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


# ── ADAPTIVE FUSION SCORE FOR CROWD SIGHTINGS ───────────────────────────────
# Seven evidence components with base weights. Any component whose evidence
# is absent is dropped and its weight is redistributed proportionally so
# missing evidence never penalises the score — it just reduces the basis.
#
#   Component            Base %   Present when
#   description_match    30       sighting has any description
#   location_match       20       both sighting + case have coordinates
#   time_consistency     15       both have parseable timestamps
#   clothing_match       15       case has clothing AND sighter reported clothing
#   source_reliability   10       always (defaults to anonymous tier)
#   corroboration         5       always (0 prior sightings → base score 30)
#   keyword_match         5       always (name/location keywords in description)

import math as _math

_BASE_W: dict[str, float] = {
    "description_match":  0.30,
    "location_match":     0.20,
    "time_consistency":   0.15,
    "clothing_match":     0.15,
    "source_reliability": 0.10,
    "corroboration":      0.05,
    "keyword_match":      0.05,
}

_RELIABILITY: dict[str, float] = {
    "official":   100.0,
    "police":     95.0,
    "hospital":   90.0,
    "volunteer":  75.0,
    "community":  70.0,
    "public":     45.0,
    "anonymous":  20.0,
}

_LABEL: dict[str, str] = {
    "description_match":  "Description / RAG match",
    "location_match":     "Location match",
    "time_consistency":   "Time feasibility",
    "clothing_match":     "Clothing similarity",
    "source_reliability": "Source reliability",
    "corroboration":      "Corroboration",
    "keyword_match":      "Keyword match",
}


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    phi1, phi2 = _math.radians(lat1), _math.radians(lat2)
    dphi = _math.radians(lat2 - lat1)
    dlam = _math.radians(lng2 - lng1)
    a = (_math.sin(dphi / 2) ** 2
         + _math.cos(phi1) * _math.cos(phi2) * _math.sin(dlam / 2) ** 2)
    return 2 * R * _math.asin(_math.sqrt(a))


def _distance_score(dist_km: float) -> float:
    if dist_km < 0.5:   return 100.0
    if dist_km < 1.0:   return 90.0
    if dist_km < 3.0:   return 80.0
    if dist_km < 5.0:   return 70.0
    if dist_km < 10.0:  return 55.0
    if dist_km < 20.0:  return 40.0
    if dist_km < 50.0:  return 20.0
    return 5.0


def _time_consistency_score(sighting: dict, child: dict) -> float | None:
    """0–100 feasibility score, or None when timestamps are absent/unparseable."""
    from datetime import datetime as _dt
    seen_at   = (sighting.get("seen_at")    or "").strip()
    last_seen = (child.get("last_seen_time") or "").strip()
    if not seen_at or not last_seen:
        return None
    fmts = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")
    t_sight = t_last = None
    for f in fmts:
        try:
            t_sight = _dt.strptime(seen_at.strip(), f)
            break
        except ValueError:
            pass
    for f in fmts:
        try:
            t_last = _dt.strptime(last_seen.strip(), f)
            break
        except ValueError:
            pass
    if t_sight is None or t_last is None:
        return None
    if t_sight < t_last:
        return 0.0  # before the disappearance — physically impossible
    hrs = (t_sight - t_last).total_seconds() / 3600.0
    # If coordinates exist, check travel-speed plausibility
    try:
        dist = _haversine(float(sighting["lat"]), float(sighting["lng"]),
                          float(child["lat"]),    float(child["lng"]))
        spd = dist / max(hrs, 0.05)
        if spd > 120.0: return 5.0    # faster than any road vehicle
        if spd > 60.0:  return 50.0   # highway speed — marginal
        if spd > 20.0:  return 75.0   # vehicle / fast travel
        return 95.0                    # walking pace — very plausible
    except (KeyError, TypeError, ValueError):
        pass
    if hrs <= 6:    return 95.0
    if hrs <= 24:   return 80.0
    if hrs <= 72:   return 60.0
    if hrs <= 168:  return 40.0
    return 20.0


def score_sighting(sighting: dict, case: dict, all_leads: list[dict]) -> dict:
    """
    Adaptive fusion confidence score for a crowd-sourced sighting.

    Weights normalise over available evidence — absent components don't
    penalise the score; their weight redistributes to what exists.
    Returns scored-lead fields including a per-component breakdown.
    """
    child = case.get("child", {})
    raw_scores: dict[str, float] = {}
    base_weights: dict[str, float] = {}

    desc      = (sighting.get("description") or "").strip()
    desc_toks = _tokens(desc)

    # ── 1. Description / RAG match (30%) ─────────────────────────────────
    # Retrieve case attributes as the reference document; compare the incoming
    # sighting against it with Jaccard token overlap (deterministic RAG).
    case_doc = " ".join(filter(None, [
        child.get("name", ""),
        child.get("clothing", ""),
        child.get("distinguishing_features", ""),
        child.get("last_seen_location", ""),
    ]))
    if desc:
        sim = _jaccard(_tokens(case_doc), desc_toks)
        raw_scores["description_match"] = min(100.0, sim * 350)
        base_weights["description_match"] = _BASE_W["description_match"]

    # ── 2. Location match (20%) ───────────────────────────────────────────
    try:
        dist = _haversine(float(sighting["lat"]), float(sighting["lng"]),
                          float(child["lat"]),    float(child["lng"]))
        raw_scores["location_match"] = _distance_score(dist)
        base_weights["location_match"] = _BASE_W["location_match"]
    except (KeyError, TypeError, ValueError):
        pass

    # ── 3. Time consistency (15%) ─────────────────────────────────────────
    tc = _time_consistency_score(sighting, child)
    if tc is not None:
        raw_scores["time_consistency"] = tc
        base_weights["time_consistency"] = _BASE_W["time_consistency"]

    # ── 4. Clothing similarity (15%) ──────────────────────────────────────
    case_cloth  = (child.get("clothing") or "").strip()
    sight_cloth = (sighting.get("clothing_observed") or "").strip()
    if case_cloth and sight_cloth:
        sim = _jaccard(_tokens(case_cloth), _tokens(sight_cloth))
        raw_scores["clothing_match"] = min(100.0, sim * 300)
        base_weights["clothing_match"] = _BASE_W["clothing_match"]

    # ── 5. Source reliability (10%) — always present ─────────────────────
    stype = (sighting.get("sighter_type") or "anonymous").lower().strip()
    raw_scores["source_reliability"] = _RELIABILITY.get(stype, 45.0)
    base_weights["source_reliability"] = _BASE_W["source_reliability"]

    # ── 6. Corroboration (5%) ────────────────────────────────────────────
    prior = [l for l in all_leads if l.get("is_sighting")]
    overlap = sum(1 for l in prior
                  if _jaccard(_tokens(l.get("snippet", "")), desc_toks) > 0.12)
    raw_scores["corroboration"] = min(100.0, 30.0 + overlap * 25.0)
    base_weights["corroboration"] = _BASE_W["corroboration"]

    # ── 7. Keyword match (5%) ────────────────────────────────────────────
    name_parts = [p for p in child.get("name", "").split() if len(p) > 1]
    loc_parts  = [p.strip() for p in re.split(r"[,/]", child.get("last_seen_location", "")) if p.strip()]
    kw_hits = _contains_any(desc, name_parts + loc_parts)
    raw_scores["keyword_match"] = 100.0 if kw_hits else 0.0
    base_weights["keyword_match"] = _BASE_W["keyword_match"]

    # ── Adaptive normalisation ────────────────────────────────────────────
    total_w = sum(base_weights[k] for k in raw_scores)
    if not total_w:
        final, eff_w = 50.0, {}
    else:
        eff_w  = {k: base_weights[k] / total_w for k in raw_scores}
        final  = sum(raw_scores[k] * eff_w[k] for k in raw_scores)

    final = max(0.0, min(100.0, final))

    breakdown = {
        k: {
            "got":   round(raw_scores[k] * eff_w.get(k, 0)),
            "max":   round(100 * eff_w.get(k, 0)),
            "label": _LABEL.get(k, k),
            "raw":   round(raw_scores[k]),
        }
        for k in raw_scores
    }

    return {
        "match_score":      round(final),
        "breakdown":        breakdown,
        "on_topic":         True,
        "is_sighting":      True,
        "sighter_type":     stype,
        "adaptive_weights": {k: f"{eff_w.get(k, 0) * 100:.0f}%" for k in raw_scores},
        "components_used":  list(raw_scores.keys()),
    }


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
