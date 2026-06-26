"""Sources: query construction and the can't-fail offline fallback (geocoding lives in geo)."""
import asyncio

import settings
import sources

CHILD = {"category": "child", "name": "Aarav Sharma",
         "last_seen_location": "Marina Beach, Chennai", "clothing": "red striped t-shirt"}


def test_build_query_includes_name_and_place():
    q = sources.build_query({"key": "news"}, CHILD)
    assert "Aarav Sharma" in q and "Marina Beach" in q and "missing" in q
    assert "Aarav Sharma" in sources.build_query({"key": "records"}, CHILD)


def test_locale_routes_by_region():
    assert sources._locale({"last_seen_location": "Marina Beach, Chennai"})[1] == "IN"
    assert sources._locale({"last_seen_location": "Brooklyn, New York"})[1] == "US"
    assert sources._locale({"last_seen_location": "Mitte, Berlin"})[1] == "DE"
    assert sources._locale({"last_seen_location": "Atlantis"})[1] == "US"   # neutral default


def test_offline_fallback_always_returns_raw_leads():
    scanned, leads = asyncio.run(sources._fetch_offline(sources.CHANNELS[0], CHILD))
    assert scanned > 0 and len(leads) >= 1
    # fetchers now return RAW leads (no geo yet) — geocoding happens upstream
    assert all("title" in l and "url" in l and "source_name" in l for l in leads)


def test_fetch_channel_degrades_when_source_raises(monkeypatch):
    async def boom(channel, child):
        raise RuntimeError("network down")
    monkeypatch.setattr(settings, "OFFLINE", False)
    monkeypatch.setitem(sources._FETCHERS, "gnews", boom)
    scanned, leads = asyncio.run(sources.fetch_channel(sources.CHANNELS[0], CHILD))
    assert len(leads) >= 1  # fell back to the offline set instead of crashing
