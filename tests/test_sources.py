"""Sources: query construction, geocoding, and the can't-fail offline fallback."""
import asyncio

import sources


def test_build_query_includes_name_and_place():
    child = {"category": "child", "name": "Aarav Sharma", "last_seen_location": "Marina Beach, Chennai"}
    q = sources.build_query({"key": "news"}, child)
    assert "Aarav Sharma" in q and "Marina Beach" in q and "missing" in q
    # records channel keeps name + place too
    assert "Aarav Sharma" in sources.build_query({"key": "records"}, child)


def test_geocode_prefers_specific_place():
    lat, lng, place = sources.geocode("seen near Marina Beach last night")
    assert place == "Marina Beach"
    assert 12 < lat < 14 and 79 < lng < 81


def test_geocode_unknown_returns_none():
    assert sources.geocode("somewhere with no known landmark") is None


def test_enrich_plots_a_point():
    lead = sources.enrich({"title": "child seen at Triplicane", "url": "u", "snippet": ""},
                          {"last_seen_location": "Chennai"})
    assert lead["place"] == "Triplicane"
    assert lead["lat"] is not None and lead["lng"] is not None


def test_offline_fallback_always_returns_leads():
    child = sources.DEMO_CASES["child"]
    scanned, leads = asyncio.run(sources._fetch_offline(sources.CHANNELS[0], child))
    assert scanned > 0 and len(leads) >= 1
    assert all("lat" in l and "url" in l for l in leads)


def test_fetch_channel_degrades_when_source_raises(monkeypatch):
    async def boom(channel, child):
        raise RuntimeError("network down")
    monkeypatch.setitem(sources._FETCHERS, "gnews", boom)
    monkeypatch.setattr(sources, "OFFLINE", False)
    scanned, leads = asyncio.run(sources.fetch_channel(sources.CHANNELS[0], sources.DEMO_CASES["child"]))
    assert len(leads) >= 1  # fell back to the offline set instead of crashing
