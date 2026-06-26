"""
LifeFind — reverse search.

Flip the question: someone reports a *sighting*, and we check it against the open
cases LifeFind already knows about. Deterministic token + age matching — a match
is a lead for the police to verify, never a confirmation.
"""
from __future__ import annotations

import re


def _toks(s: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _coverage(small: set[str], big: set[str]) -> float:
    """How much of the smaller token set is covered by the larger (0..1)."""
    if not small or not big:
        return 0.0
    return len(small & big) / len(small)


def match_sighting(sighting: dict, cases: list[dict]) -> list[dict]:
    """Rank known cases by how well they match a sighting.
    score = location 50 + description/clothing 35 + age 15. Below 20 is dropped."""
    s_loc = _toks(sighting.get("location"))
    s_desc = _toks(f"{sighting.get('description', '')} {sighting.get('clothing', '')}")
    s_age = (sighting.get("age") or "").strip()

    out: list[dict] = []
    for case in cases:
        ch = case.get("child", {}) or {}
        c_loc = _toks(ch.get("last_seen_location"))
        c_desc = _toks(f"{ch.get('clothing', '')} {ch.get('distinguishing_features', '')}")
        loc = _coverage(s_loc, c_loc) if s_loc else 0.0
        desc = _coverage(s_desc, c_desc) if s_desc else 0.0
        age = 0.0
        c_age = (ch.get("age") or "").strip()
        if s_age.isdigit() and c_age.isdigit():
            age = 1.0 if abs(int(s_age) - int(c_age)) <= 3 else 0.0
        score = round(loc * 50 + desc * 35 + age * 15)
        if score < 20:
            continue
        out.append({
            "case_id": case.get("id"), "name": ch.get("name") or "Unknown",
            "category": ch.get("category"), "last_seen_location": ch.get("last_seen_location"),
            "score": score,
            "breakdown": {"location": round(loc * 50), "description": round(desc * 35), "age": round(age * 15)},
        })
    out.sort(key=lambda x: -x["score"])
    return out[:10]
