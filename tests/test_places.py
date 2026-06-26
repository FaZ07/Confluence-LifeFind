"""CCTV discovery — Overpass query build + element parsing (no network)."""
import places


def test_build_query_targets_the_point():
    q = places._build_query(13.05, 80.28, 1200)
    assert "around:1200,13.05,80.28" in q
    assert "amenity=fuel" in q and "railway=station" in q


def test_classify_maps_known_tags():
    assert places._classify({"amenity": "fuel"}) == "Petrol bunk"
    assert places._classify({"railway": "station"}) == "Railway station"
    assert places._classify({"weird": "thing"}) == "Place"


def test_parse_sorts_dedups_and_labels():
    lat, lng = 13.050, 80.280
    elements = [
        {"lat": 13.060, "lon": 80.290, "tags": {"amenity": "atm", "name": "City ATM"}},
        {"lat": 13.0505, "lon": 80.2805, "tags": {"amenity": "fuel", "name": "HP Petrol"}},
        {"lat": 13.0505, "lon": 80.2805, "tags": {"amenity": "fuel", "name": "HP Petrol"}},  # dup
        {"tags": {"shop": "mall"}},  # no coords -> dropped
    ]
    out = places._parse(elements, lat, lng)
    assert out[0]["name"] == "HP Petrol" and out[0]["kind"] == "Petrol bunk"  # nearest first
    assert out[0]["dist_m"] < out[1]["dist_m"]
    names = [p["name"] for p in out]
    assert names.count("HP Petrol") == 1        # de-duplicated
    assert all("lat" in p and "dist_m" in p for p in out)
