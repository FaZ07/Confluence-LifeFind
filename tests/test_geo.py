"""Geocoding: offline gazetteer, gazetteer build, and lead placement (no network in tests)."""
import asyncio

import geo
import settings


def test_offline_lookup_prefers_specific_place():
    lat, lng, place = geo.offline_lookup("seen near Marina Beach last night")
    assert place == "Marina Beach"
    assert 12 < lat < 14 and 79 < lng < 81


def test_offline_lookup_unknown_returns_none():
    assert geo.offline_lookup("a place with no known landmark at all") is None


def test_geocode_unknown_without_network_is_none(monkeypatch):
    monkeypatch.setattr(settings, "GEOCODE_ENABLED", False)
    assert asyncio.run(geo.geocode("Nowhere-Town-XYZ-123")) is None


def test_build_gazetteer_splits_neighbourhood_and_city(monkeypatch):
    monkeypatch.setattr(settings, "GEOCODE_ENABLED", False)
    gaz = asyncio.run(geo.build_gazetteer("Marina Beach, Chennai"))
    assert gaz["center"][2] == "Marina Beach"   # map centers on the specific spot
    assert gaz["city"] == "Chennai"             # city is the broad fallback / generic
    assert "chennai" in gaz["places"]


def test_locate_lead_specific_vs_city_fallback(monkeypatch):
    monkeypatch.setattr(settings, "GEOCODE_ENABLED", False)
    gaz = asyncio.run(geo.build_gazetteer("Marina Beach, Chennai"))
    # lead naming a specific place -> pinned there (stays distinct from the city)
    a = geo.locate_lead({"title": "child seen at Triplicane", "url": "u1"}, gaz)
    assert a["place"] == "Triplicane" and a["lat"] is not None
    # lead with no known place -> falls back to the CITY, not the last-seen spot
    b = geo.locate_lead({"title": "no landmark mentioned here", "url": "u2"}, gaz)
    assert b["place"] == "Chennai"
