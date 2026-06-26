"""Statistical search-radius model — grounded lost-person-behavior rings."""
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
