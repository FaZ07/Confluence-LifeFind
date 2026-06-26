"""
LifeFind — geocoding.

Works for ANY city on earth: a place name resolves via OpenStreetMap Nominatim
(cached in-process, rate-limited to OSM's 1 req/sec policy). A built-in offline
gazetteer is tried first, so common places are instant and the app still plots a
map with no network at all.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

import httpx

import settings

log = logging.getLogger("lifefind.geo")

Coord = tuple[float, float, str]

# Offline gazetteer — instant, no network. Seeded India/Chennai-heavy (the demo
# region); everywhere else resolves live via Nominatim.
OFFLINE_PLACES: dict[str, Coord] = {
    "marina beach": (13.050, 80.282, "Marina Beach"), "triplicane": (13.060, 80.271, "Triplicane"),
    "chepauk": (13.063, 80.275, "Chepauk"), "chennai central": (13.082, 80.275, "Chennai Central"),
    "t. nagar": (13.041, 80.233, "T. Nagar"), "t nagar": (13.041, 80.233, "T. Nagar"),
    "pondy bazaar": (13.040, 80.234, "Pondy Bazaar"), "mambalam": (13.038, 80.222, "West Mambalam"),
    "adyar": (13.006, 80.257, "Adyar"), "velachery": (12.979, 80.221, "Velachery"),
    "tambaram": (12.925, 80.127, "Tambaram"), "egmore": (13.078, 80.261, "Egmore"),
    "guindy": (13.011, 80.220, "Guindy"), "anna nagar": (13.086, 80.210, "Anna Nagar"),
    "mylapore": (13.034, 80.268, "Mylapore"), "besant nagar": (12.999, 80.267, "Besant Nagar"),
    "vadapalani": (13.050, 80.212, "Vadapalani"), "nungambakkam": (13.060, 80.242, "Nungambakkam"),
    "saidapet": (13.021, 80.223, "Saidapet"), "porur": (13.038, 80.158, "Porur"),
    "ambattur": (13.098, 80.161, "Ambattur"), "avadi": (13.115, 80.101, "Avadi"),
    "perambur": (13.111, 80.233, "Perambur"), "royapettah": (13.053, 80.264, "Royapettah"),
    "chennai": (13.060, 80.250, "Chennai"), "madurai": (9.925, 78.119, "Madurai"),
    "coimbatore": (11.017, 76.956, "Coimbatore"), "trichy": (10.790, 78.704, "Tiruchirappalli"),
    "tiruchirappalli": (10.790, 78.704, "Tiruchirappalli"), "salem": (11.664, 78.146, "Salem"),
    "vellore": (12.916, 79.132, "Vellore"), "erode": (11.341, 77.717, "Erode"),
    "tirunelveli": (8.713, 77.756, "Tirunelveli"), "pondicherry": (11.930, 79.830, "Pondicherry"),
    "puducherry": (11.930, 79.830, "Puducherry"),
    "andhra": (15.913, 79.740, "Andhra Pradesh"), "bengaluru": (12.972, 77.595, "Bengaluru"),
    "bangalore": (12.972, 77.595, "Bengaluru"), "indiranagar": (12.971, 77.640, "Indiranagar"),
    "hyderabad": (17.385, 78.487, "Hyderabad"), "mumbai": (19.076, 72.878, "Mumbai"),
    "delhi": (28.614, 77.209, "Delhi"), "kolkata": (22.573, 88.364, "Kolkata"),
    "kochi": (9.931, 76.267, "Kochi"), "kerala": (10.310, 76.330, "Kerala"),
    "chalakudy": (10.310, 76.330, "Chalakudy"),
}

_CACHE: dict[str, Coord | None] = {}
_last_call = 0.0
_lock = asyncio.Lock()


def offline_lookup(text: str) -> Coord | None:
    """Substring-match the longest known place name in a piece of text."""
    low = (text or "").lower()
    for key in sorted(OFFLINE_PLACES, key=len, reverse=True):
        if key in low:
            return OFFLINE_PLACES[key]
    return None


def _short_label(display: str, fallback: str) -> str:
    return (display.split(",")[0].strip() or fallback).strip()


async def _nominatim(query: str) -> Coord | None:
    global _last_call
    async with _lock:  # serialize + throttle to honour OSM's 1 req/sec policy
        wait = settings.GEOCODE_MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT, follow_redirects=True) as client:
            r = await client.get(
                settings.NOMINATIM_BASE,
                params={"q": query, "format": "json", "limit": 1, "addressdetails": 0},
                headers={"User-Agent": settings.USER_AGENT},
            )
            r.raise_for_status()
            arr = r.json()
            if not arr:
                return None
            top = arr[0]
            return (round(float(top["lat"]), 5), round(float(top["lon"]), 5),
                    _short_label(top.get("display_name", ""), query))
    except Exception as e:  # noqa: BLE001 — geocoding is best-effort
        log.warning("nominatim failed for %r: %s", query, e)
        return None


async def geocode(query: str) -> Coord | None:
    """Resolve a place name to (lat, lng, label). Cache -> offline -> Nominatim."""
    q = (query or "").strip()
    if not q:
        return None
    key = q.lower()
    if key in _CACHE:
        return _CACHE[key]
    hit = offline_lookup(q)
    if hit is None and settings.GEOCODE_ENABLED and not settings.offline_now():
        hit = await _nominatim(q)
    _CACHE[key] = hit
    if len(_CACHE) > settings.GEOCODE_CACHE_MAX:   # bound memory; evict oldest
        _CACHE.pop(next(iter(_CACHE)))
    return hit


async def build_gazetteer(case_location: str) -> dict:
    """Geocode the case's last-seen location and its parts (bounded, cached).
    Distinguishes the specific last-seen spot (map center) from the broad CITY,
    which is the only label treated as 'city-level' for fusion / fallback.
    Returns {center, city, city_coord, places{name_lower: Coord}}."""
    places: dict[str, Coord] = {}
    center: Coord | None = None
    parts = [p.strip() for p in re.split(r"[,/]", case_location or "") if p.strip()]
    # the city is the broadest part (last), but only when a more specific part exists
    city_name = parts[-1] if len(parts) >= 2 else (parts[0] if parts else "")
    queries = ([case_location.strip()] if (case_location or "").strip() else []) + parts
    seen: set[str] = set()
    for q in queries:
        if len(places) >= settings.GEOCODE_MAX_LOOKUPS:
            break
        k = q.lower()
        if k in seen:
            continue
        seen.add(k)
        hit = await geocode(q)
        if hit:
            places[k] = hit
            if center is None:
                center = hit
    city_coord = await geocode(city_name) if city_name else None
    if center is None:
        center = city_coord
    city_label = city_coord[2] if city_coord else city_name
    return {"center": center, "city": city_label,
            "city_coord": city_coord or center, "places": places}


def locate_lead(lead: dict, gazetteer: dict, center: Coord | None = None) -> dict:
    """Assign lat/lng/place to a lead deterministically:
        offline table  ->  a case-gazetteer place named in the text  ->  the case
        CITY (broad fallback). Genuine specific places stay distinct from the
        city-level fallback so fusion stays meaningful."""
    center = center or gazetteer.get("center")
    city = gazetteer.get("city")
    text = f"{lead.get('title', '')} {lead.get('snippet', '')}"
    hit = offline_lookup(text)
    if hit is None:
        low = text.lower()
        for name, coords in (gazetteer.get("places") or {}).items():
            if name and name in low:
                hit = coords
                break
    if hit is None:
        hit = gazetteer.get("city_coord") or center or OFFLINE_PLACES["chennai"]
    lat, lng, label = hit
    specific = bool(label) and label != city          # city-level fallback spreads wider
    h = abs(hash(lead.get("url", "") + lead.get("title", "")))
    jx = ((h % 1000) / 1000.0 - 0.5)
    jy = (((h // 1000) % 1000) / 1000.0 - 0.5)
    spread = 0.014 if specific else 0.055
    lead["lat"] = round(lat + jy * spread, 5)
    lead["lng"] = round(lng + jx * spread, 5)
    lead["place"] = label
    return lead
