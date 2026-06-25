"""
LifeFind — investigation-support analysis.

Everything here is deterministic and computed straight from the scored, geocoded
leads. It turns isolated clues into evidence:

  * corroboration  — N independent sources agreeing on a place / clothing / age
  * movement       — chronological sequence of REPORTED locations (report order,
                     framed honestly — not a claim the subject physically moved)
  * cluster        — weighted centre of activity + a radius covering most signal
  * search_area    — primary / secondary areas + transport hubs + corridor
  * contradictions — conflicting appearance descriptions across sources

No ML, no black box. A responder can ask "where did this number come from?" and
the answer is arithmetic over the leads.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime

_TRANSIT = ("station", "central", "junction", "terminus", "terminal", "bus stand",
            "bus stop", "airport", "metro", "seaport", "depot", "interchange", "railway")
_COLORS = ("red", "blue", "green", "black", "white", "yellow", "orange", "grey", "gray",
           "brown", "pink", "purple", "maroon", "navy", "beige", "cream", "golden", "silver")


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lat1, lng1), (lat2, lng2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(x)))


def _parse(d: str | None):
    try:
        return datetime.strptime((d or "")[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _span_label(d0: str, d1: str) -> str:
    a, b = _parse(d0), _parse(d1)
    if not a or not b:
        return ""
    days = (b - a).days
    if days <= 0:
        return "the same day"
    return "24 hours" if days == 1 else f"{days} days"


def _specific(lead: dict, gen: set[str]) -> bool:
    p = (lead.get("place") or "").strip()
    return bool(p) and p not in gen


# ----------------------------------------------------------------------
def corroboration(leads: list[dict], child: dict, gen: set[str]) -> list[dict]:
    """Independent agreement across sources on location, clothing or age."""
    out: list[dict] = []

    by_place: dict[str, list[dict]] = defaultdict(list)
    for l in leads:
        if _specific(l, gen):
            by_place[l["place"]].append(l)
    for place, ls in by_place.items():
        srcs = sorted({l.get("source_name", "") for l in ls if l.get("source_name")})
        if len(srcs) >= 2:
            dates = sorted(d for d in (l.get("date", "") for l in ls) if d)
            window = _span_label(dates[0], dates[-1]) if len(dates) >= 2 else ""
            detail = f"{len(srcs)} independent sources reference {place}"
            detail += f" within {window}." if window else "."
            out.append({"type": "location", "value": place, "source_count": len(srcs),
                        "sources": srcs, "window": window, "detail": detail})

    for token in [c.strip().lower() for c in re.split(r"[,;]", child.get("clothing", "")) if c.strip()]:
        srcs = sorted({l.get("source_name", "") for l in leads
                       if token in f"{l.get('title', '')} {l.get('snippet', '')}".lower()
                       and l.get("source_name")})
        if len(srcs) >= 2:
            out.append({"type": "clothing", "value": token, "source_count": len(srcs),
                        "sources": srcs, "detail": f"{len(srcs)} sources mention \"{token}\"."})

    age = (child.get("age") or "").strip()
    if age.isdigit():
        srcs = sorted({l.get("source_name", "") for l in leads
                       if re.search(rf"\b{age}\b", f"{l.get('title', '')} {l.get('snippet', '')}")
                       and l.get("source_name")})
        if len(srcs) >= 2:
            out.append({"type": "age", "value": age, "source_count": len(srcs),
                        "sources": srcs, "detail": f"{len(srcs)} sources cite age {age}."})

    out.sort(key=lambda x: -x["source_count"])
    return out[:6]


# ----------------------------------------------------------------------
def movement(leads: list[dict], gen: set[str]) -> dict | None:
    """Chronological sequence of REPORTED locations (earliest mention each).
    Honest framing: this is report order, not a tracked physical path."""
    earliest: dict[str, dict] = {}
    for l in leads:
        if not _specific(l, gen) or l.get("lat") is None:
            continue
        p, d = l["place"], l.get("date", "")
        cur = earliest.get(p)
        if cur is None or (d and d < cur["date"]):
            earliest[p] = {"place": p, "date": d, "lat": l["lat"], "lng": l["lng"]}
    pts = sorted(earliest.values(), key=lambda v: (v["date"] or "9999", v["place"]))
    if len(pts) < 2:
        return None
    legs = [{"from": a["place"], "to": b["place"],
             "km": round(_haversine_km((a["lat"], a["lng"]), (b["lat"], b["lng"])), 1)}
            for a, b in zip(pts, pts[1:])]
    span = _span_label(pts[0]["date"], pts[-1]["date"])
    seq = " → ".join(p["place"] for p in pts)
    detail = (f"Reports place the subject across {len(pts)} locations"
              + (f" over {span}" if span else "") + f": {seq}.")
    return {"path": pts, "legs": legs, "span": span, "detail": detail}


# ----------------------------------------------------------------------
def _ranked_places(leads: list[dict], gen: set[str]) -> list[dict]:
    g: dict[str, dict] = {}
    for l in leads:
        if not _specific(l, gen) or l.get("lat") is None:
            continue
        e = g.setdefault(l["place"], {"place": l["place"], "score": 0, "lat": 0.0, "lng": 0.0, "n": 0})
        e["score"] += l.get("match_score", 0)
        e["lat"] += l["lat"]; e["lng"] += l["lng"]; e["n"] += 1
    out = [{"place": e["place"], "score": e["score"],
            "lat": round(e["lat"] / e["n"], 5), "lng": round(e["lng"] / e["n"], 5)}
           for e in g.values()]
    out.sort(key=lambda x: -x["score"])
    return out


def cluster(leads: list[dict]) -> dict | None:
    """Weighted centre of activity + the radius covering ~80% of weighted signal."""
    pts = [(l["lat"], l["lng"], max(1, l.get("match_score", 0)))
           for l in leads if l.get("lat") is not None]
    if len(pts) < 2:
        return None
    total = sum(w for *_, w in pts)
    clat = sum(la * w for la, _, w in pts) / total
    clng = sum(ln * w for _, ln, w in pts) / total
    dists = sorted((_haversine_km((clat, clng), (la, ln)), w) for la, ln, w in pts)
    target, cum, radius = 0.8 * total, 0.0, dists[-1][0]
    for dist, w in dists:
        cum += w
        if cum >= target:
            radius = dist
            break
    radius = round(max(radius, 0.3), 1)
    covered = sum(w for dist, w in dists if dist <= radius)
    pct = round(100 * covered / total)
    anchor = min((l for l in leads if l.get("lat") is not None),
                 key=lambda l: _haversine_km((clat, clng), (l["lat"], l["lng"])),
                 default={}).get("place", "the area")
    return {"lat": round(clat, 5), "lng": round(clng, 5), "radius_km": radius,
            "coverage_pct": pct, "anchor": anchor,
            "detail": f"{pct}% of weighted signal falls within {radius} km of {anchor}."}


# ----------------------------------------------------------------------
def search_area(leads: list[dict], mvmt: dict | None, clust: dict | None, gen: set[str]) -> dict | None:
    ranked = _ranked_places(leads, gen)
    if not ranked:
        return None
    base = clust["radius_km"] if clust else 1.5

    def area(z, factor):
        return None if not z else {"place": z["place"], "lat": z["lat"], "lng": z["lng"],
                                   "radius_km": round(max(0.6, base * factor), 1)}

    hubs, seen = [], set()
    for l in leads:
        p = l.get("place")
        text = f"{p or ''} {l.get('title', '')}".lower()
        if p and p not in seen and l.get("lat") is not None and any(k in text for k in _TRANSIT):
            seen.add(p)
            hubs.append({"place": p, "lat": l["lat"], "lng": l["lng"]})

    primary = ranked[0]
    secondary = ranked[1] if len(ranked) > 1 else None
    detail = f"Primary search area: {primary['place']}"
    detail += f"; secondary: {secondary['place']}." if secondary else "."
    return {
        "primary": area(primary, 1.0),
        "secondary": area(secondary, 1.3),
        "transport_hubs": hubs[:5],
        "corridor": [[p["lat"], p["lng"]] for p in (mvmt["path"] if mvmt else [])],
        "detail": detail,
    }


# ----------------------------------------------------------------------
def contradictions(leads: list[dict], child: dict) -> list[dict]:
    """Surface conflicting appearance descriptions across credible leads."""
    def norm(c):
        return "grey" if c == "gray" else c

    stated = {norm(c) for c in _COLORS if re.search(rf"\b{c}\b", (child.get("clothing", "")).lower())}
    found: dict[str, set[str]] = defaultdict(set)
    for l in leads:
        if l.get("match_score", 0) < 35:
            continue
        text = f"{l.get('title', '')} {l.get('snippet', '')}".lower()
        for c in _COLORS:
            if re.search(rf"\b{c}\b", text):
                found[norm(c)].add(l.get("source_name", ""))

    if not stated:
        return []
    conflict = sorted(c for c in found if c not in stated)
    if not conflict:
        return []
    srcs = sorted({s for c in conflict for s in found[c] if s})
    return [{
        "attribute": "appearance", "stated": sorted(stated), "conflicting": conflict, "sources": srcs,
        "detail": (f"Possible conflict: case describes {', '.join(sorted(stated))}, "
                   f"but sources mention {', '.join(conflict)}."),
    }]


# ----------------------------------------------------------------------
def build(leads: list[dict], child: dict, gen: set[str]) -> dict:
    """Full investigation-support payload merged into the intelligence object."""
    mvmt = movement(leads, gen)
    clust = cluster(leads)
    return {
        "corroboration": corroboration(leads, child, gen),
        "movement": mvmt,
        "cluster": clust,
        "search_area": search_area(leads, mvmt, clust, gen),
        "contradictions": contradictions(leads, child),
    }
