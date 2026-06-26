"""
LifeFind — statistical, time-aware search-radius model.

This is the grounded, defensible version of "predict where to search next": the
empirical distance rings that real search-and-rescue teams use. Given the point
last seen and the subject category, it returns the radii within which a given
fraction of comparable subjects have *historically* been found — from published
lost-person-behavior statistics (Koester, *Lost Person Behavior*; ISRID).

Time awareness (the difference-maker): a person cannot be farther from the point
last seen than they could physically have travelled. We bound the historical
distribution by a mobility horizon (an effective net-dispersal speed × elapsed
time), so the search area starts tight right after the disappearance and grows,
saturating at the full historical distribution once enough time has passed. The
rings stay nested and the numbers are reproducible — the same case at the same
elapsed time always yields the same radii.

It is explicitly NOT a prediction of where this individual is, and NOT an AI
guess. The radii and speeds are representative figures — calibrate them to your
own region and dataset before any operational use. We deliberately do not model
exact roads/evacuation routes, which can't be grounded reliably from public data.
"""
from __future__ import annotations

from datetime import datetime

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

# Effective net-dispersal speed (km/h) — NOT walking speed: it is net displacement
# from the last-seen point, which is far slower because people wander, rest and
# backtrack. Representative; calibrate locally. Drives how fast the area saturates.
SPEED_KMH: dict[str, float] = {
    "child": 1.2, "dementia": 1.6, "tourist": 2.5, "disaster": 1.2, "missing": 1.8,
}

# Floor on the saturation fraction so t≈0 still shows a usable immediate-vicinity
# area rather than a zero-radius point.
MIN_FACTOR = 0.10

_BASIS = ("Published lost-person-behavior (ISRID) statistics, bounded by an effective "
          "mobility horizon (speed × elapsed time) — representative, calibrate locally; "
          "not a prediction of the individual.")

_TIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S")


def elapsed_hours(last_seen_time: str | None, now: datetime | None = None) -> float | None:
    """Hours between the last-seen time and `now` (default: current time).
    Returns None if the time is missing/unparseable; clamps future times to 0."""
    if not last_seen_time:
        return None
    seen = None
    for fmt in _TIME_FORMATS:
        try:
            seen = datetime.strptime(last_seen_time.strip(), fmt)
            break
        except (ValueError, AttributeError):
            continue
    if seen is None:
        return None
    delta = ((now or datetime.now()) - seen).total_seconds() / 3600.0
    return max(0.0, delta)


def _factor(p95_km: float, speed_kmh: float, hours: float | None) -> float:
    """Saturation fraction in [MIN_FACTOR, 1.0]. 1.0 when elapsed time is unknown
    (fall back to the full historical distribution)."""
    if hours is None or not p95_km:
        return 1.0
    horizon = speed_kmh * hours          # furthest they could plausibly have dispersed
    return min(1.0, max(MIN_FACTOR, horizon / p95_km))


def rings(category: str, lat: float | None, lng: float | None,
          last_seen_time: str | None = None, now: datetime | None = None) -> dict | None:
    """Time-aware distance rings (50/75/95% historical find radius) anchored on the
    point last seen and bounded by how far the subject could have travelled by now.
    Returns None if the case isn't geolocated. With no `last_seen_time`, returns the
    full historical distribution (identical to the original behaviour)."""
    if lat is None or lng is None:
        return None
    key = category if category in RINGS_KM else "missing"
    r = RINGS_KM[key]
    speed = SPEED_KMH[key]
    hours = elapsed_hours(last_seen_time, now)
    factor = _factor(r["p95"], speed, hours)

    full = [{"p": 50, "km": r["p50"]}, {"p": 75, "km": r["p75"]}, {"p": 95, "km": r["p95"]}]
    scaled = [{"p": x["p"], "km": round(x["km"] * factor, 2)} for x in full]

    return {
        "category": key,
        "center": [lat, lng],
        "rings": scaled,
        "full_rings": full,                 # historical saturation extent (animation target)
        "time_aware": hours is not None,
        "elapsed_hours": round(hours, 1) if hours is not None else None,
        "saturated": factor >= 1.0,
        "speed_kmh": speed,                 # lets the client animate growth deterministically
        "p95_km": r["p95"],
        "min_factor": MIN_FACTOR,
        "note": r["note"],
        "basis": _BASIS,
    }
