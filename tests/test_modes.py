"""Per-request Live/Demo data-source override (settings.offline_now / use_offline)."""
import settings


def teardown_function():
    settings.use_offline(None)   # never leak the override into other tests


def test_default_follows_offline_setting(monkeypatch):
    settings.use_offline(None)
    monkeypatch.setattr(settings, "OFFLINE", True)
    assert settings.offline_now() is True
    monkeypatch.setattr(settings, "OFFLINE", False)
    assert settings.offline_now() is False


def test_per_request_override_wins(monkeypatch):
    monkeypatch.setattr(settings, "OFFLINE", True)   # default = demo
    settings.use_offline(False)                       # ...but this request asked for live
    assert settings.offline_now() is False
    settings.use_offline(True)
    assert settings.offline_now() is True
    settings.use_offline(None)                        # back to the default
    assert settings.offline_now() is True
