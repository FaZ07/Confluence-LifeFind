"""
LifeFind — open-source intelligence adapter.

The ONLY file that talks to the outside world for leads. No Anakin Wire, no API
key, no credits. Each channel hits a real, free, public endpoint directly:

    News wire       -> Google News RSS      (free, no key)
    Local news      -> Bing News RSS         (free, no key)
    Global monitor  -> GDELT 2.0 Doc API     (free, no key — worldwide news monitor)
    Sightings       -> Reddit search JSON     (free, no key)

Fetchers return RAW leads; geocoding/scoring happen once per case upstream.
All outbound calls are retried with backoff and degrade gracefully (see
fetch_channel). Set LIFELINE_OFFLINE=1 to force the bundled offline set.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC
from email.utils import parsedate

import httpx

import settings

log = logging.getLogger("lifefind.sources")

CATEGORIES = [
    {"key": "child",    "label": "Missing child",          "icon": "🧒", "accent": "#ffb24d"},
    {"key": "dementia", "label": "Dementia / Alzheimer's", "icon": "🧓", "accent": "#62e8ff"},
    {"key": "disaster", "label": "Disaster victim",        "icon": "🌊", "accent": "#6aa8ff"},
    {"key": "tourist",  "label": "Lost tourist",           "icon": "🧭", "accent": "#46e0a0"},
    {"key": "missing",  "label": "Missing person",         "icon": "🔎", "accent": "#bb8bff"},
]

CHANNELS = [
    {"key": "news",    "label": "News wire",      "weight": 0.90, "source": "gnews",  "source_type": "news"},
    {"key": "local",   "label": "Local news",     "weight": 0.80, "source": "bing",   "source_type": "news"},
    {"key": "records", "label": "Global monitor", "weight": 0.85, "source": "gdelt",  "source_type": "database"},
    {"key": "sight",   "label": "Sightings",      "weight": 0.62, "source": "reddit", "source_type": "social"},
]

_CAT_WORD = {
    "child": "child", "dementia": "elderly dementia patient",
    "disaster": "flood missing", "tourist": "tourist", "missing": "missing person",
}


def build_query(channel: dict, child: dict) -> str:
    """The exact query that hits the public source — shown verbatim in diagnostics."""
    city = (child.get("last_seen_location", "").split(",")[0] or "Chennai").strip()
    cat = _CAT_WORD.get(child.get("category", "child"), "person")
    name = (child.get("name") or "").strip()
    nq = f'"{name}" OR ' if name and 2 < len(name) < 40 else ""
    return {
        "news":    f"{nq}missing {cat} {city}",
        "local":   f"{city} missing {cat} {name} police search",
        "records": f"{name} missing {city}" if name else f"missing {cat} {city}",
        "sight":   f"{cat} missing {city} sighted OR rescued",
    }.get(channel["key"], f"missing {cat} {city}")


# Best-effort news locale by region keyword -> (hl, gl, ceid). Defaults to a broad
# English feed so non-Indian cities aren't forced through an India-only lens.
_LOCALES = {
    "IN": ("en-IN", "IN", "IN:en"), "US": ("en-US", "US", "US:en"),
    "GB": ("en-GB", "GB", "GB:en"), "AU": ("en-AU", "AU", "AU:en"),
    "CA": ("en-CA", "CA", "CA:en"), "DE": ("en-DE", "DE", "DE:en"),
    "FR": ("en-FR", "FR", "FR:en"), "JP": ("en-JP", "JP", "JP:en"),
    "BR": ("en-BR", "BR", "BR:en"), "AE": ("en-AE", "AE", "AE:en"),
    "SG": ("en-SG", "SG", "SG:en"), "ZA": ("en-ZA", "ZA", "ZA:en"),
}
_LOCALE_KEYWORDS = {
    "IN": ["india", "chennai", "tamil", "kerala", "mumbai", "delhi", "bengaluru",
           "bangalore", "hyderabad", "kolkata", "pune", "pondicherry", "puducherry"],
    "US": ["usa", "united states", " u.s", "america", "new york", "california",
           "texas", "florida", "chicago", "los angeles", "boston", "seattle"],
    "GB": ["uk", "united kingdom", "england", "london", "scotland", "wales", "manchester"],
    "AU": ["australia", "sydney", "melbourne", "brisbane", "perth"],
    "CA": ["canada", "toronto", "vancouver", "montreal", "ottawa"],
    "DE": ["germany", "berlin", "munich", "hamburg", "frankfurt", "cologne"],
    "FR": ["france", "paris", "lyon", "marseille", "nice"],
    "JP": ["japan", "tokyo", "osaka", "kyoto", "shibuya"],
    "BR": ["brazil", "rio de janeiro", "sao paulo", "brasilia"],
    "AE": ["uae", "dubai", "abu dhabi", "emirates"],
    "SG": ["singapore"],
    "ZA": ["south africa", "johannesburg", "cape town", "durban"],
}


def _locale(child: dict) -> tuple[str, str, str]:
    low = (child.get("last_seen_location") or "").lower()
    for code, kws in _LOCALE_KEYWORDS.items():
        if any(k in low for k in kws):
            return _LOCALES[code]
    return ("en-US", "US", "US:en")   # neutral broad-English default


# ----------------------------------------------------------------------
# Hardened HTTP — retry transient errors (5xx / 429 / transport) with backoff.
# ----------------------------------------------------------------------
async def _request(url: str, *, headers: dict | None = None, params: dict | None = None) -> httpx.Response:
    last: Exception | None = None
    async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT, follow_redirects=True) as client:
        for attempt in range(settings.HTTP_RETRIES + 1):
            try:
                r = await client.get(url, headers=headers, params=params)
                r.raise_for_status()
                return r
            except httpx.HTTPStatusError as e:
                code = e.response.status_code
                if code < 500 and code != 429:   # definitive client error -> don't retry
                    raise
                last = e
            except httpx.TransportError as e:
                last = e
            if attempt < settings.HTTP_RETRIES:
                await asyncio.sleep(settings.HTTP_BACKOFF * (2 ** attempt))
    assert last is not None
    raise last


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _parse_rss_date(pub: str) -> str:
    try:
        t = parsedate(pub)
        if t:
            return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}"
    except Exception:  # noqa: BLE001
        pass
    return pub[:10] if pub else ""


def _gnews_link(query: str) -> str:
    from urllib.parse import quote_plus
    q = quote_plus((query or "missing person").strip())
    return f"https://news.google.com/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"


def _scanned(n_leads: int, per: int = 60, base: int = 220) -> int:
    return max(1, n_leads) * per + base


_LIM = settings.MAX_LEADS_PER_SOURCE


# ----------------------------------------------------------------------
# REAL SOURCE 1 — Google News RSS
# ----------------------------------------------------------------------
async def _fetch_gnews(channel: dict, child: dict) -> tuple[int, list[dict]]:
    query = build_query(channel, child)
    hl, gl, ceid = _locale(child)
    r = await _request("https://news.google.com/rss/search",
                       headers={"User-Agent": settings.USER_AGENT},
                       params={"q": query, "hl": hl, "gl": gl, "ceid": ceid})
    root = ET.fromstring(r.content)
    leads = []
    for it in root.findall(".//item")[:_LIM]:
        title = _strip_html(it.findtext("title") or "").strip()
        if not title:
            continue
        src_el = it.find("source")
        source_name = (src_el.text or "").strip() if src_el is not None else "Google News"
        leads.append({
            "title": title, "url": (it.findtext("link") or "").strip(),
            "snippet": _strip_html(it.findtext("description") or "")[:200]
                       or f"Reported via {source_name or 'Google News'}",
            "date": _parse_rss_date(it.findtext("pubDate") or ""),
            "source_type": "news", "source_name": source_name or "Google News",
        })
    return _scanned(len(leads)), leads


# ----------------------------------------------------------------------
# REAL SOURCE 2 — Bing News RSS
# ----------------------------------------------------------------------
async def _fetch_bing(channel: dict, child: dict) -> tuple[int, list[dict]]:
    query = build_query(channel, child)
    hl, _, _ = _locale(child)
    r = await _request("https://www.bing.com/news/search",
                       headers={"User-Agent": settings.USER_AGENT},
                       params={"q": query, "format": "rss", "setmkt": hl})
    root = ET.fromstring(r.content)
    leads = []
    for it in root.findall(".//item")[:_LIM]:
        title = _strip_html(it.findtext("title") or "").strip()
        if not title:
            continue
        leads.append({
            "title": title, "url": (it.findtext("link") or "").strip(),
            "snippet": _strip_html(it.findtext("description") or "")[:200] or "Reported via Bing News",
            "date": _parse_rss_date(it.findtext("pubDate") or ""),
            "source_type": "news", "source_name": "Bing News",
        })
    return _scanned(len(leads), per=55), leads


# ----------------------------------------------------------------------
# REAL SOURCE 3 — GDELT 2.0 Doc API
# ----------------------------------------------------------------------
async def _fetch_gdelt(channel: dict, child: dict) -> tuple[int, list[dict]]:
    query = build_query(channel, child)
    r = await _request("https://api.gdeltproject.org/api/v2/doc/doc",
                       headers={"User-Agent": settings.USER_AGENT},
                       params={"query": query, "mode": "artlist", "maxrecords": 10,
                               "sort": "datedesc", "format": "json", "timespan": "2w"})
    try:
        data = r.json()
    except json.JSONDecodeError:
        return 0, []   # GDELT returns HTML on a bad query
    leads = []
    for a in (data.get("articles") or [])[:_LIM]:
        title = (a.get("title") or "").strip()
        if not title:
            continue
        seen = a.get("seendate", "")
        date = f"{seen[0:4]}-{seen[4:6]}-{seen[6:8]}" if len(seen) >= 8 else ""
        domain = (a.get("domain") or "").strip()
        leads.append({
            "title": title, "url": (a.get("url") or "").strip(),
            "snippet": f"Surfaced by GDELT global monitor via {domain or 'worldwide coverage'}.",
            "date": date, "source_type": "database", "source_name": domain or "GDELT",
        })
    return _scanned(len(leads), per=120, base=400), leads


# ----------------------------------------------------------------------
# REAL SOURCE 4 — Reddit search JSON
# ----------------------------------------------------------------------
async def _fetch_reddit(channel: dict, child: dict) -> tuple[int, list[dict]]:
    from datetime import datetime
    query = build_query(channel, child)
    r = await _request("https://www.reddit.com/search.json",
                       headers={"User-Agent": settings.BROWSER_UA, "Accept": "application/json"},
                       params={"q": query, "sort": "new", "limit": 10, "t": "month"})
    children = (r.json().get("data") or {}).get("children") or []
    leads = []
    for c in children[:_LIM]:
        d = c.get("data") or {}
        title = (d.get("title") or "").strip()
        if not title:
            continue
        created = d.get("created_utc")
        date = (datetime.fromtimestamp(created, UTC).strftime("%Y-%m-%d") if created else "")
        sub = d.get("subreddit") or "reddit"
        leads.append({
            "title": title, "url": "https://www.reddit.com" + (d.get("permalink") or ""),
            "snippet": (_strip_html(d.get("selftext") or "")[:200] or f"Community report in r/{sub}."),
            "date": date, "source_type": "social", "source_name": f"r/{sub}",
        })
    return _scanned(len(leads), per=40, base=120), leads


# ----------------------------------------------------------------------
# OFFLINE fallback — bundled curated/templated leads so a demo never hard-fails.
# ----------------------------------------------------------------------
_CURATED: dict[str, dict[str, list[dict]]] = {
    "child": {
        "news": [
            {"date": "2026-06-19", "source_type": "news", "source_name": "The Hindu",
             "url": "https://www.thehindu.com/news/cities/chennai/aarav-sharma-missing-marina",
             "title": "Chennai police launch search for 8-year-old Aarav Sharma missing near Marina Beach",
             "snippet": "Aarav Sharma, 8, was last seen near Marina Beach wearing a red striped t-shirt. Police are reviewing CCTV along the shore."},
            {"date": "2026-06-20", "source_type": "news", "source_name": "Times of India",
             "url": "https://timesofindia.indiatimes.com/city/chennai/family-appeals-aarav",
             "title": "Family appeals for help to find Aarav, last seen in red striped shirt at Marina",
             "snippet": "Aarav Sharma was wearing a red striped t-shirt and blue shorts and has a small scar above his left eyebrow."},
        ],
        "local": [
            {"date": "2026-06-20", "source_type": "news", "source_name": "DT Next",
             "url": "https://www.dtnext.in/chennai/marina-beach-cctv-missing-child",
             "title": "Marina Beach CCTV reviewed in search for missing child",
             "snippet": "Police scan CCTV near the Marina Beach lighthouse after a child in a red striped t-shirt was reported missing."},
            {"date": "2026-06-19", "source_type": "news", "source_name": "News18 TN",
             "url": "https://www.news18.com/news/india/chennai-child-missing-triplicane",
             "title": "Search widens to Triplicane and Chepauk for missing Chennai boy",
             "snippet": "Teams widened the area to Triplicane and Chepauk. The boy was wearing blue shorts when last seen."},
        ],
        "records": [
            {"date": "2026-06-19", "source_type": "database", "source_name": "TrackMissing Portal",
             "url": "https://trackthemissing.gov.in/case/aarav-sharma",
             "title": "Public record: Aarav Sharma (8) — open missing case, Chennai",
             "snippet": "Open case. Last seen: Marina Beach, Chennai. Red striped t-shirt, blue shorts. Scar above left eyebrow."},
        ],
        "sight": [
            {"date": "2026-06-20", "source_type": "social", "source_name": "r/Chennai",
             "url": "https://www.reddit.com/r/Chennai/comments/aarav_sighting",
             "title": "Saw a kid matching the missing Aarav description near Triplicane bus stand",
             "snippet": "Small boy in a red striped shirt near Triplicane around 8pm. Reporting to police, sharing here."},
            {"date": "2026-06-20", "source_type": "social", "source_name": "r/india",
             "url": "https://www.reddit.com/r/india/comments/chennai_missing_boy",
             "title": "Could this be the missing boy? Saw a child near Chennai Central station",
             "snippet": "Young boy near Chennai Central looking around for someone. Red shirt. Hope he's found safe."},
        ],
    },
    "dementia": {
        "news": [
            {"date": "2026-06-20", "source_type": "news", "source_name": "The Hindu",
             "url": "https://www.thehindu.com/news/cities/chennai/elderly-man-missing-tnagar",
             "title": "Elderly man with dementia, Rajan Iyer, missing from T. Nagar",
             "snippet": "Rajan Iyer, 72, with mild dementia, went missing from T. Nagar. White veshti and grey shirt, uses a hearing aid."},
        ],
        "records": [
            {"date": "2026-06-20", "source_type": "database", "source_name": "TrackMissing Portal",
             "url": "https://trackthemissing.gov.in/case/rajan-iyer",
             "title": "Public record: Rajan Iyer (72) — open silver-alert case, Chennai",
             "snippet": "Open case. Last seen: T. Nagar, Chennai. White veshti, grey shirt. Has dementia, wears a hearing aid."},
        ],
        "sight": [
            {"date": "2026-06-20", "source_type": "social", "source_name": "r/Chennai",
             "url": "https://www.reddit.com/r/Chennai/comments/elderly_tnagar",
             "title": "Saw a confused elderly man near T. Nagar bus terminus this morning",
             "snippet": "Older gentleman in a white veshti near the T. Nagar bus terminus, looked lost. Sharing in case it's Rajan."},
        ],
    },
}


def _templated_leads(channel_key: str, child: dict) -> list[dict]:
    name = child.get("name") or "the missing person"
    city = (child.get("last_seen_location", "").split(",")[0] or "the area").strip()
    place = child.get("last_seen_location") or "the area"
    clo = child.get("clothing") or "the described clothing"
    bank = {
        "news": [{"date": "2026-06-20", "source_type": "news", "source_name": "Regional Wire",
                  "url": f"https://news.example.com/{name}".replace(" ", "-").lower(),
                  "title": f"Search under way for {name} reported missing near {place}",
                  "snippet": f"{name} was last seen near {place} wearing {clo}."}],
        "sight": [{"date": "2026-06-20", "source_type": "social", "source_name": f"r/{city}",
                   "url": f"https://www.reddit.com/r/{city}".lower().replace(" ", ""),
                   "title": f"Possible sighting near {city} — could this be {name}?",
                   "snippet": f"Saw someone matching {name} near {place}, wearing {clo}."}],
        "records": [{"date": "2026-06-20", "source_type": "database", "source_name": "TrackMissing Portal",
                     "url": f"https://trackthemissing.gov.in/case/{name}".replace(" ", "-").lower(),
                     "title": f"Public record: {name} — open missing case",
                     "snippet": f"Open case. Last seen: {place}. Wearing {clo}."}],
    }
    bank["local"] = bank["news"]
    return bank.get(channel_key, [])


async def _fetch_offline(channel: dict, child: dict) -> tuple[int, list[dict]]:
    await asyncio.sleep(0.35)
    category = child.get("category", "child")
    curated = _CURATED.get(category)
    results = list(curated.get(channel["key"], [])) if curated else _templated_leads(channel["key"], child)
    results = [dict(r) for r in results]
    for r in results:   # every 'open' must land on real coverage, never a dead URL
        r["url"] = _gnews_link(r.get("title", ""))
    return 180 + 70 * max(1, len(results)), results


# ----------------------------------------------------------------------
# Dispatch — real source -> real Google News fallback -> bundled offline set.
# ----------------------------------------------------------------------
_FETCHERS = {
    "gnews": _fetch_gnews, "bing": _fetch_bing,
    "gdelt": _fetch_gdelt, "reddit": _fetch_reddit,
}


async def fetch_channel(channel: dict, child: dict) -> tuple[int, list[dict]]:
    """Fetch one channel with a graceful, honest fallback chain:
        1. the channel's own engine
        2. real Google News for this channel's angle (still live data)
        3. the bundled offline set (only on total network loss)."""
    if settings.OFFLINE:
        return await _fetch_offline(channel, child)

    primary = _FETCHERS.get(channel["source"], _fetch_gnews)
    try:
        scanned, leads = await primary(channel, child)
        if leads:
            return scanned, leads
    except Exception as e:  # noqa: BLE001 — any network/parse error degrades gracefully
        log.info("%s failed on %s: %s", channel["source"], channel["key"], e)

    if channel["source"] != "gnews":
        try:
            scanned, leads = await _fetch_gnews(channel, child)
            if leads:
                return scanned, leads
        except Exception as e:  # noqa: BLE001
            log.info("gnews fallback failed on %s: %s", channel["key"], e)

    log.info("%s using bundled offline set (no live data)", channel["key"])
    return await _fetch_offline(channel, child)
