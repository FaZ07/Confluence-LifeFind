"""Statistical search-radius model — grounded, time-aware lost-person-behavior rings."""
from datetime import datetime, timedelta

import searchmodel


def test_rings_increase_with_probability():
    out = searchmodel.rings("child", 13.05, 80.28)
    km = [r["km"] for r in out["rings"]]
    assert [r["p"] for r in out["rings"]] == [50, 75, 95]
    assert km[0] < km[1] < km[2]            # 50% radius < 75% < 95%
    assert out["center"] == [13.05, 80.28]
    assert "ISRID" in out["basis"] or "lost-person" in out["basis"].lower()


def test_unknown_category_falls_back_to_missing():
    out = searchmodel.rings("banana", 13.0, 80.0)
    assert out["category"] == "missing"


def test_none_center_returns_none():
    assert searchmodel.rings("child", None, None) is None


def test_each_category_has_three_rings():
    for cat in ("child", "dementia", "tourist", "disaster", "missing"):
        out = searchmodel.rings(cat, 1.0, 1.0)
        assert len(out["rings"]) == 3 and out["note"]


# ---- time awareness ----

def test_no_time_returns_full_historical_distribution():
    """Backward compatible: with no last-seen time, the rings are the full figures."""
    out = searchmodel.rings("child", 13.0, 80.0)
    assert out["time_aware"] is False
    assert [r["km"] for r in out["rings"]] == [1.0, 2.0, 5.0]   # unchanged historical values


def test_rings_grow_with_elapsed_time():
    """Soon after the disappearance the area is tight; later it is wider."""
    now = datetime(2026, 6, 20, 12, 0)
    seen = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    early = searchmodel.rings("child", 13.0, 80.0, seen, now=now)
    seen_late = (now - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")
    late = searchmodel.rings("child", 13.0, 80.0, seen_late, now=now)
    assert early["time_aware"] is True and early["elapsed_hours"] == 1.0
    assert early["rings"][2]["km"] < late["rings"][2]["km"]      # 95% ring grows over time
    assert early["rings"][0]["km"] < early["rings"][1]["km"] < early["rings"][2]["km"]  # stays nested


def test_saturates_at_historical_distribution():
    """Given enough time, the time-aware rings recover the full historical figures."""
    now = datetime(2026, 6, 20, 12, 0)
    seen = (now - timedelta(hours=72)).strftime("%Y-%m-%d %H:%M")
    out = searchmodel.rings("child", 13.0, 80.0, seen, now=now)
    assert out["saturated"] is True
    assert [r["km"] for r in out["rings"]] == [1.0, 2.0, 5.0]


def test_unparseable_or_future_time_is_safe():
    now = datetime(2026, 6, 20, 12, 0)
    assert searchmodel.rings("child", 13.0, 80.0, "not-a-date", now=now)["time_aware"] is False
    future = (now + timedelta(hours=5)).strftime("%Y-%m-%d %H:%M")
    out = searchmodel.rings("child", 13.0, 80.0, future, now=now)
    assert out["elapsed_hours"] == 0.0                          # clamped, not negative
