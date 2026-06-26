"""
LifeFind — CCTV / footage-source discovery.

NOT face recognition and NOT camera feeds. Just the public places that commonly
run CCTV — petrol bunks, ATMs/banks, railway & bus stations, supermarkets, malls,
marketplaces and any mapped public cameras — within walking distance of the point
last seen, from OpenStreetMap (free, no key). Search teams otherwise burn time
working this out on the ground; this hands them the list to go request footage.
"""
from __future__ import annotations

import logging

import httpx

import settings
from analysis import _haversine_km

log = logging.getLogger("lifefind.places")

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# OSM (key, value) -> friendly label for places that typically have usable CCTV.
_KINDS: dict[tuple[str, str], str] = {
    ("amenity", "fuel"): "Petrol bunk",
    ("amenity", "atm"): "ATM",
    ("amenity", "bank"): "Bank",
    ("railway", "station"): "Railway station",
    ("amenity", "bus_station"): "Bus station",
    ("man_made", "surveillance"): "Public camera",
    ("shop", "supermarket"): "Supermarket",
    ("shop", "mall"): "Shopping mall",
    ("amenity", "marketplace"): "Market",
}


def _build_query(lat: float, lng: float, radius_m: int) -> str:
    sel = "".join(f"node[{k}={v}](around:{radius_m},{lat},{lng});" for (k, v) in _KINDS)
    return f"[out:json][timeout:20];({sel});out body 80;"


def _classify(tags: dict) -> str:
    for (k, v), label in _KINDS.items():
        if tags.get(k) == v:
            return label
    return "Place"


def _parse(elements: list[dict], lat: float, lng: float, limit: int = 40) -> list[dict]:
    rows = []
    for e in elements:
        elat, elng = e.get("lat"), e.get("lon")
        if elat is None or elng is None:
            continue
        tags = e.get("tags") or {}
        kind = _classify(tags)
        rows.append({
            "kind": kind, "name": tags.get("name") or kind,
            "lat": elat, "lng": elng,
            "dist_m": round(_haversine_km((lat, lng), (elat, elng)) * 1000),
        })
    rows.sort(key=lambda x: x["dist_m"])
    seen, out = set(), []
    for p in rows:
        key = (p["name"], p["kind"], round(p["lat"], 4), round(p["lng"], 4))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
        if len(out) >= limit:
            break
    return out


async def nearby(lat: float, lng: float, radius_m: int = 1200, limit: int = 40) -> list[dict]:
    """Query OpenStreetMap (Overpass) for CCTV-likely places near a point.
    Returns [] gracefully on any failure (mirror down, rate-limited, timeout)."""
    query = _build_query(lat, lng, radius_m)
    for url in OVERPASS_URLS:
        try:
            async with httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT + 10) as client:
                r = await client.post(url, data={"data": query},
                                      headers={"User-Agent": settings.USER_AGENT})
                r.raise_for_status()
                return _parse(r.json().get("elements") or [], lat, lng, limit)
        except Exception as e:  # noqa: BLE001 — try the next mirror, then degrade to []
            log.info("overpass failed (%s): %s", url, e)
    return []
