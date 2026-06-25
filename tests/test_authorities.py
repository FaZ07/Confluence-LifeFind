"""Authority handoff: region detection + channel surfacing."""
import authorities


def test_detect_country():
    assert authorities.detect_country("Marina Beach, Chennai") == "IN"
    assert authorities.detect_country("Brooklyn, New York") == "US"
    assert authorities.detect_country("Camden, London") == "GB"
    assert authorities.detect_country("Atlantis") == "global"


def test_for_location_returns_regional_plus_global():
    out = authorities.for_location("T. Nagar, Chennai")
    assert out["country"] == "IN"
    names = [c["name"] for c in out["channels"]]
    assert any("Childline" in n for n in names)        # regional
    assert any("INTERPOL" in n for n in names)         # global tail
    assert out["note"]


def test_unknown_location_still_gives_global_channels():
    out = authorities.for_location("somewhere unmapped")
    assert out["country"] == "global"
    assert len(out["channels"]) >= 1
