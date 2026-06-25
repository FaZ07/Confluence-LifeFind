"""Investigation-support engine: corroboration, movement, clustering, area, contradictions."""
import analysis

GEN = {"Chennai"}


def _leads():
    return [
        {"id": "1", "place": "Triplicane", "lat": 13.060, "lng": 80.270, "date": "2026-06-20",
         "source_name": "The Hindu", "match_score": 88, "title": "boy seen at Triplicane in red shirt", "snippet": "red shirt"},
        {"id": "2", "place": "Triplicane", "lat": 13.061, "lng": 80.271, "date": "2026-06-20",
         "source_name": "r/Chennai", "match_score": 70, "title": "Triplicane sighting red shirt", "snippet": ""},
        {"id": "3", "place": "Triplicane", "lat": 13.059, "lng": 80.269, "date": "2026-06-21",
         "source_name": "DT Next", "match_score": 60, "title": "Triplicane bus stand checked", "snippet": ""},
        {"id": "4", "place": "Marina Beach", "lat": 13.050, "lng": 80.282, "date": "2026-06-19",
         "source_name": "Times of India", "match_score": 80, "title": "Marina Beach last seen", "snippet": ""},
        {"id": "5", "place": "Chennai Central", "lat": 13.082, "lng": 80.275, "date": "2026-06-21",
         "source_name": "News18", "match_score": 55, "title": "near Chennai Central station", "snippet": ""},
        {"id": "6", "place": "Triplicane", "lat": 13.062, "lng": 80.272, "date": "2026-06-21",
         "source_name": "r/india", "match_score": 50, "title": "man in green jacket seen", "snippet": "green jacket"},
    ]


CHILD = {"clothing": "red shirt, blue shorts", "age": "8"}


def test_corroboration_location_and_clothing():
    out = analysis.corroboration(_leads(), CHILD, GEN)
    loc = [c for c in out if c["type"] == "location"]
    assert loc and loc[0]["value"] == "Triplicane" and loc[0]["source_count"] >= 3
    assert any(c["type"] == "clothing" and c["value"] == "red shirt" for c in out)


def test_movement_is_chronological():
    mv = analysis.movement(_leads(), GEN)
    assert mv is not None
    places = [p["place"] for p in mv["path"]]
    assert places == ["Marina Beach", "Triplicane", "Chennai Central"]
    assert len(mv["legs"]) == 2 and all(leg["km"] >= 0 for leg in mv["legs"])


def test_cluster_has_center_and_radius():
    cl = analysis.cluster(_leads())
    assert cl is not None
    assert cl["radius_km"] > 0 and 0 < cl["coverage_pct"] <= 100
    assert 12 < cl["lat"] < 14 and 79 < cl["lng"] < 81


def test_search_area_primary_hubs_corridor():
    leads = _leads()
    sa = analysis.search_area(leads, analysis.movement(leads, GEN), analysis.cluster(leads), GEN)
    assert sa["primary"]["place"] == "Triplicane"        # highest total signal
    assert sa["secondary"]["place"] == "Marina Beach"
    assert any(h["place"] in ("Triplicane", "Chennai Central") for h in sa["transport_hubs"])
    assert len(sa["corridor"]) == 3                       # follows the movement path


def test_contradiction_detected():
    cons = analysis.contradictions(_leads(), CHILD)
    assert cons and "green" in cons[0]["conflicting"]
    assert "red" in cons[0]["stated"]


def test_no_contradiction_when_consistent():
    leads = [l for l in _leads() if l["id"] != "6"]   # drop the green-jacket lead
    assert analysis.contradictions(leads, CHILD) == []


def test_build_returns_all_keys():
    out = analysis.build(_leads(), CHILD, GEN)
    assert set(out) == {"corroboration", "movement", "cluster", "search_area", "contradictions"}
