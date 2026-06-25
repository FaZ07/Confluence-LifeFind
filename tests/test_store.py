"""Persistence: save/load round-trip + TTL purge + graceful behaviour."""
import settings
import store


def _case(cid="abc12345"):
    return {"id": cid, "child": {"name": "Aarav"}, "leads": [{"id": "x", "match_score": 80}],
            "done": True, "intelligence": {"commander": {"priority_zones": []}}}


def test_save_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(settings, "PERSIST", True)
    assert store.init() is True
    c = _case()
    store.save(c)
    loaded = store.load(c["id"])
    assert loaded is not None
    assert loaded["child"]["name"] == "Aarav"
    assert loaded["leads"][0]["match_score"] == 80


def test_load_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "t2.db"))
    monkeypatch.setattr(settings, "PERSIST", True)
    store.init()
    assert store.load("does-not-exist") is None


def test_purge_expired_removes_old(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "t3.db"))
    monkeypatch.setattr(settings, "PERSIST", True)
    monkeypatch.setattr(settings, "CASE_TTL_DAYS", -1)  # cutoff in the future -> purge all
    store.init()
    store.save(_case("old00001"))
    assert store.purge_expired() >= 1


def test_disabled_store_is_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "t4.db"))
    monkeypatch.setattr(settings, "PERSIST", False)
    assert store.init() is False
    store.save(_case())          # must not raise
    assert store.load("abc12345") is None
