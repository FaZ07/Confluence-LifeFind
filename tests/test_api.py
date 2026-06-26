"""End-to-end API tests over the real FastAPI surface (the unit tests don't cover HTTP)."""
import asyncio
import base64
import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as appmod
import intel
import settings
from scoring import score_lead


@pytest.fixture
def client(monkeypatch):
    # offline + no persistence -> deterministic, no network, no db file
    monkeypatch.setattr(settings, "OFFLINE", True)
    monkeypatch.setattr(settings, "GEOCODE_ENABLED", False)
    monkeypatch.setattr(settings, "PERSIST", False)
    appmod._HITS.clear()
    appmod.CASES.clear()
    with TestClient(appmod.app) as c:
        yield c


def _completed_case(cid="apitest01"):
    child = {"category": "child", "name": "Aarav Sharma", "age": "8",
             "last_seen_location": "Marina Beach, Chennai", "clothing": "red striped t-shirt"}
    case = {"id": cid, "child": child, "leads": [], "sources_searched": 500, "elapsed_s": 1.2,
            "done": True, "geocoded": True, "diagnostics": [], "intelligence": None, "error": None}
    raw = [
        {"title": "Aarav seen at Marina Beach in red striped t-shirt", "snippet": "red striped t-shirt",
         "url": "http://x/1", "date": "2026-06-20", "source_type": "news", "source_name": "The Hindu",
         "lat": 13.050, "lng": 80.282, "place": "Marina Beach"},
        {"title": "Family appeals, Aarav last seen near Marina Beach", "snippet": "",
         "url": "http://x/2", "date": "2026-06-20", "source_type": "news", "source_name": "Times of India",
         "lat": 13.051, "lng": 80.281, "place": "Marina Beach"},
    ]
    case["leads"] = [score_lead(r, case, 0.9) for r in raw]
    case["intelligence"] = intel.analyze_case(case["leads"], child, {"Chennai"})
    return case


def test_health(client):
    j = client.get("/api/health").json()
    assert j["status"] == "ok" and j["vision"] is True and "Sightings" in str(j["sources"])


def test_categories_and_demo(client):
    assert len(client.get("/api/categories").json()) >= 5
    assert client.get("/api/demo-case?category=child").json()["category"] == "child"


def test_search_validation_requires_name_or_location(client):
    r = client.post("/api/search", json={"category": "child", "name": "", "last_seen_location": ""})
    assert r.status_code == 422


def test_search_starts_and_unknown_case_404(client):
    r = client.post("/api/search", json={"name": "Test Person", "last_seen_location": "Chennai"})
    assert r.status_code == 200 and "case_id" in r.json()
    assert client.get("/api/case/nope1234").status_code == 404


def test_rate_limit_kicks_in(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MIN", 2)
    codes = [client.post("/api/search", json={"name": "A", "last_seen_location": "Chennai"}).status_code
             for _ in range(4)]
    assert 429 in codes


def test_run_search_offline_completes(monkeypatch):
    monkeypatch.setattr(settings, "OFFLINE", True)
    monkeypatch.setattr(settings, "GEOCODE_ENABLED", False)
    monkeypatch.setattr(settings, "PERSIST", False)
    cid = "runsearch1"
    appmod.CASES[cid] = {"id": cid, "child": appmod.DEMO_CASES["child"], "leads": [],
                         "sources_searched": 0, "elapsed_s": 0.0, "done": False, "geocoded": False,
                         "diagnostics": [], "intelligence": None, "error": None}
    asyncio.run(appmod.run_search(cid))
    case = appmod.CASES[cid]
    assert case["done"] is True
    assert case["error"] is None
    assert len(case["leads"]) > 0
    assert case["intelligence"]["commander"] is not None


def test_vision_endpoint_detects_red(client):
    b = io.BytesIO(); Image.new("RGB", (80, 80), (205, 25, 25)).save(b, "PNG")
    data = "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()
    r = client.post("/api/vision/colors", json={"image": data})
    assert r.status_code == 200 and r.json()["colors"][0]["name"] == "red"


def test_vision_endpoint_rejects_garbage(client):
    assert client.post("/api/vision/colors", json={"image": ""}).status_code == 422
    assert client.post("/api/vision/colors",
                       json={"image": base64.b64encode(b"not an image").decode()}).status_code == 422


def test_completed_case_read_endpoints(client):
    case = _completed_case(); appmod.CASES[case["id"]] = case; cid = case["id"]
    assert client.get(f"/api/case/{cid}").json()["done"] is True
    chat = client.post(f"/api/case/{cid}/chat", json={"message": "why marina beach?"}).json()["response"]
    assert "Marina Beach" in chat
    assert client.post(f"/api/case/{cid}/search-plan").status_code == 200
    assert client.get(f"/api/case/{cid}/authorities").json()["country"] == "IN"
    csv = client.get(f"/api/case/{cid}/export.csv")
    assert csv.status_code == 200 and "match_score" in csv.text
    assert "MISSING" in client.get(f"/api/case/{cid}/dossier").text


def test_lead_status_update_and_chat_validation(client):
    case = _completed_case("apitest02"); appmod.CASES[case["id"]] = case; cid = case["id"]
    lid = case["leads"][0]["id"]
    assert client.post(f"/api/case/{cid}/lead/{lid}/status", json={"status": "verified"}).status_code == 200
    assert client.post(f"/api/case/{cid}/lead/ghost/status", json={"status": "x"}).status_code == 404
    assert client.post(f"/api/case/{cid}/chat", json={"message": ""}).status_code == 422
