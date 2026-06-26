"""
LifeFind — statistical search-radius model.

This is the grounded, defensible version of "predict where to search next": the
empirical distance rings that real search-and-rescue teams use. Given the point
last seen and the subject category, it returns the radii within which a given
fraction of comparable subjects have *historically* been found — from published
lost-person-behavior statistics (Koester, *Lost Person Behavior*; ISRID).

It is explicitly NOT a prediction of where this individual is, and NOT an AI
guess. The radii are representative figures — calibrate them to your own region
and dataset before any operational use. We deliberately do not model exact
roads/evacuation routes, which can't be grounded reliably from public data.
"""
from __future__ import annotations

# (50%, 75%, 95%) historical find-distance in km from the point last seen.
# Representative values drawn from published lost-person-behavior distributions.
RINGS_KM: dict[str, dict] = {
    "child":    {"p50": 1.0, "p75": 2.0, "p95": 5.0,
                 "note": "Young children stay close; older children range further. Check immediate surroundings, water and barriers first."},
    "dementia": {"p50": 0.8, "p75": 2.0, "p95": 7.9,
                 "note": "Often follow roads/paths in one direction and can travel surprisingly far before being found; check transit lines and where paths funnel."},
    "tourist":  {"p50": 1.5, "p75": 4.0, "p95": 13.0,
                 "note": "Mobile and transit-dependent; widen along transport routes and toward landmarks."},
    "disaster": {"p50": 1.0, "p75": 3.0, "p95": 10.0,
                 "note": "Movement shaped by evacuation routes, water and barriers; check shelters and high ground."},
    "missing":  {"p50": 1.2, "p75": 3.5, "p95": 12.0,
                 "note": "General missing-adult distribution; widen along roads and transit."},
}
_BASIS = "Published lost-person-behavior (ISRID) statistics — representative, calibrate locally; not a prediction of the individual."


def rings(category: str, lat: float | None, lng: float | None) -> dict | None:
    """Distance rings (50/75/95% historical find radius) anchored on the point
    last seen. Returns None if the case isn't geolocated."""
    if lat is None or lng is None:
        return None
    r = RINGS_KM.get(category, RINGS_KM["missing"])
    return {
        "category": category if category in RINGS_KM else "missing",
        "center": [lat, lng],
        "rings": [{"p": 50, "km": r["p50"]}, {"p": 75, "km": r["p75"]}, {"p": 95, "km": r["p95"]}],
        "note": r["note"],
        "basis": _BASIS,
    }
