"""
LifeFind — Missing Human Search Operations Console (open-source, hardened).

Real free sources (Google News, Bing, GDELT, Reddit) + a fully deterministic
intelligence layer + global geocoding + persistence + authority handoff.
No API keys, no credits, no black box.

Run:  uvicorn app:app --reload --port 8000   ->  open http://localhost:8000
"""
from __future__ import annotations

import asyncio
import base64
import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

import authorities
import export
import geo
import intel
import narrate
import places
import reverse
import searchmodel
import settings
import sources
import store
import vision
from scoring import dedup, score_lead

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("lifefind")

STATIC = Path(__file__).parent / "static"

# In-memory working set for live (streaming) cases; persisted to SQLite alongside.
CASES: dict[str, dict] = {}

# --- simple per-client rate limiter for the expensive search endpoint ---
_HITS: dict[str, list[float]] = {}


def _require_key(request: Request) -> None:
    """Optional shared-secret gate (off unless LIFELINE_API_KEY is set)."""
    if settings.API_KEY and request.headers.get("X-API-Key") != settings.API_KEY:
        raise HTTPException(401, "invalid or missing API key")


def _rate_ok(client: str) -> bool:
    now = time.time()
    hits = [t for t in _HITS.get(client, []) if t > now - 60]
    if len(hits) >= settings.RATE_LIMIT_PER_MIN:
        _HITS[client] = hits
        return False
    hits.append(now)
    _HITS[client] = hits
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init()
    removed = store.purge_expired()
    if removed:
        log.info("purged %d expired cases", removed)
    log.info("%s %s ready (offline=%s, geocode=%s, persist=%s)",
             settings.APP_NAME, settings.APP_VERSION, settings.OFFLINE,
             settings.GEOCODE_ENABLED, store.enabled())
    yield


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.ALLOW_ORIGINS,
    allow_methods=["*"], allow_headers=["*"],
)


class ChildIn(BaseModel):
    category: str = "child"
    name: str = ""
    age: str = ""
    photo_url: str = ""
    last_seen_location: str = ""
    last_seen_time: str = ""
    clothing: str = ""
    distinguishing_features: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _clean(cls, v):
        # trim + clamp every string field (defends against abuse / runaway input)
        return v.strip()[: settings.MAX_FIELD_LEN] if isinstance(v, str) else v


def _evict_old_cases() -> None:
    """Keep memory bounded — evict the oldest in-memory cases beyond the cap.
    Evicted cases remain readable from the persistent store."""
    overflow = len(CASES) - settings.MAX_ACTIVE_CASES
    if overflow <= 0:
        return
    for cid in sorted(CASES, key=lambda c: CASES[c].get("created_at", 0))[:overflow]:
        CASES.pop(cid, None)


def _get_case(case_id: str) -> dict | None:
    """Live in-memory case if present, else a persisted snapshot, else None.
    Cases older than CASE_TTL_DAYS are treated as expired (sensitive data)."""
    case = CASES.get(case_id) or store.load(case_id)
    if not case:
        return None
    if time.time() - case.get("created_at", time.time()) > settings.CASE_TTL_DAYS * 86400:
        return None
    return case


async def run_search(case_id: str) -> None:
    """Background task: geocode, fan out across channels, score, persist.
    Wrapped end-to-end so any failure still drives the case to a terminal state
    with a valid (possibly empty) intelligence payload — a case can never wedge."""
    case = CASES[case_id]
    child = case["child"]
    started = time.perf_counter()
    gaz: dict = {"center": None, "city": "", "city_coord": None, "places": {}}

    try:
        # Global geocoding: resolve the case location (any city on earth) + gazetteer.
        gaz = await geo.build_gazetteer(child.get("last_seen_location", ""))
        center = gaz.get("center")
        if center:
            child["lat"], child["lng"], child["place"] = center
        case["geocoded"] = center is not None
        # Grounded statistical search-radius rings (lost-person-behavior data),
        # bounded by how far the subject could have travelled since last seen.
        case["search_model"] = searchmodel.rings(child.get("category", "missing"),
                                                 child.get("lat"), child.get("lng"),
                                                 child.get("last_seen_time"))
        store.save(case)

        async def run_channel(channel):
            scanned, raw = await sources.fetch_channel(channel, child)
            return channel, scanned, raw

        tasks = [asyncio.ensure_future(run_channel(ch)) for ch in sources.CHANNELS]
        for coro in asyncio.as_completed(tasks):
            channel, scanned, raw = await coro
            case["sources_searched"] += scanned
            accepted = 0
            for item in raw:
                geo.locate_lead(item, gaz, center)        # plot it (global)
                lead = score_lead(item, case, channel["weight"])
                if not lead.get("on_topic"):              # drop generic noise, keep a tally
                    case["filtered"] += 1
                    continue
                if any(l["url"] == lead["url"] for l in case["leads"]):
                    continue
                case["leads"].append(lead)
                case["leads"] = dedup(case["leads"])
                accepted += 1
                if not settings.SYNC:
                    await asyncio.sleep(0.18)              # stream effect (skipped when synchronous)
            case["diagnostics"].append(
                {"channel": channel["label"], "query": sources.build_query(channel, child),
                 "status": "done", "leads": accepted})
            store.save(case)

        # Only the resolved CITY is treated as city-level (specific spot still fuses).
        generics = {gaz["city"]} if gaz.get("city") else set()
        case["intelligence"] = intel.analyze_case(case["leads"], case["child"], generics)
        cmd = (case["intelligence"] or {}).get("commander") or {}
        case["search_plan"] = intel.generate_search_plan(case["leads"], case["child"], cmd)
    except Exception as e:  # noqa: BLE001 — never leave a case wedged
        log.exception("run_search failed for %s", case_id)
        case["error"] = f"partial results — {type(e).__name__}"
    finally:
        case["elapsed_s"] = round(time.perf_counter() - started, 1)
        case["done"] = True
        if case.get("intelligence") is None:   # guarantee a terminal, valid payload
            generics = {gaz["city"]} if gaz.get("city") else set()
            try:
                case["intelligence"] = intel.analyze_case(case["leads"], case["child"], generics)
            except Exception:  # noqa: BLE001
                case["intelligence"] = intel.analyze_case([], case["child"])
        store.save(case)
        log.info("case %s done: %d leads, %.1fs%s", case_id, len(case["leads"]),
                 case["elapsed_s"], " (with errors)" if case.get("error") else "")


@app.post("/api/search")
async def start_search(child: ChildIn, request: Request):
    _require_key(request)
    client = request.client.host if request.client else "anon"
    if not _rate_ok(client):
        raise HTTPException(429, "rate limit exceeded — slow down a moment")
    if not child.name and not child.last_seen_location:
        raise HTTPException(422, "provide at least a name or a last-seen location")
    if child.category not in {c["key"] for c in sources.CATEGORIES}:
        child.category = "missing"

    case_id = secrets.token_urlsafe(12)   # unguessable — the link exposes case PII
    CASES[case_id] = {
        "id": case_id, "child": child.model_dump(), "leads": [],
        "created_at": time.time(),
        "sources_searched": 0, "elapsed_s": 0.0, "done": False,
        "geocoded": False, "diagnostics": [], "intelligence": None, "error": None,
        "search_model": None, "cctv": None, "filtered": 0, "search_plan": None,
    }
    _evict_old_cases()
    if settings.SYNC:                       # serverless: run inline, return the full case
        await run_search(case_id)
        return CASES[case_id]
    asyncio.create_task(run_search(case_id))
    return {"case_id": case_id}


@app.get("/api/case/{case_id}")
async def get_case(case_id: str):
    case = _get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return case


@app.post("/api/case/{case_id}/lead/{lead_id}/status")
async def set_lead_status(case_id: str, lead_id: str, body: dict):
    case = _get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    status = (body.get("status") or "new")[:20]
    for lead in case["leads"]:
        if lead["id"] == lead_id:
            lead["status"] = status
            if case_id not in CASES:
                store.save(case)   # restored-from-disk case: persist the change
            return {"ok": True}
    raise HTTPException(404, "lead not found")


@app.get("/api/categories")
async def categories():
    return sources.CATEGORIES


# How long ago each demo subject was "last seen" — chosen so the time-aware search
# radius opens mid-expansion (visibly growing, not yet saturated) in every demo.
_DEMO_AGE_HOURS = {"child": 1.5, "dementia": 3.0, "tourist": 2.0, "disaster": 5.0, "missing": 4.0}


@app.get("/api/demo-case")
async def demo_case(category: str = "child"):
    base = DEMO_CASES.get(category, DEMO_CASES["child"])
    demo = dict(base)
    seen = datetime.now() - timedelta(hours=_DEMO_AGE_HOURS.get(demo.get("category", "child"), 2.0))
    demo["last_seen_time"] = seen.strftime("%Y-%m-%d %H:%M")   # fresh, relative to now
    return demo


@app.post("/api/case/{case_id}/chat")
async def chat(case_id: str, body: dict):
    case = _get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    message = (body.get("message") or "").strip()[: settings.MAX_FIELD_LEN]
    if not message:
        raise HTTPException(422, "message required")
    answer = intel.chat_response(message, case)                 # deterministic
    answer = await narrate.polish(answer, child=case.get("child"))  # optional rephrase (no-op if disabled)
    return {"response": answer, "narrated": narrate.enabled()}


@app.post("/api/case/{case_id}/search-plan")
async def search_plan(case_id: str):
    case = _get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    cmd = (case.get("intelligence") or {}).get("commander") or {}
    plan = intel.generate_search_plan(case["leads"], case["child"], cmd)
    if not plan:
        raise HTTPException(503, "no priority zones established yet")
    return plan


@app.get("/api/case/{case_id}/authorities")
async def case_authorities(case_id: str):
    case = _get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return authorities.for_location(case["child"].get("last_seen_location", ""))


@app.get("/api/case/{case_id}/cctv")
async def case_cctv(case_id: str):
    """Public places that commonly run CCTV near the last-seen point (OpenStreetMap).
    Lazy + cached — Overpass is slow. Not face recognition, not camera feeds."""
    case = _get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    child = case["child"]
    lat, lng = child.get("lat"), child.get("lng")
    if lat is None or lng is None:
        raise HTTPException(409, "case is not geolocated yet")
    if case.get("cctv") is None:
        case["cctv"] = await places.nearby(lat, lng)
        if case_id in CASES:
            store.save(case)
    return {"places": case["cctv"],
            "note": "Public places that commonly run CCTV near the last-seen point. Verify on "
                    "the ground and request any footage through the proper legal channel."}


@app.get("/api/case/{case_id}/export.csv")
async def export_csv(case_id: str):
    case = _get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return PlainTextResponse(
        export.leads_csv(case), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="lifefind-{case_id}.csv"'})


@app.get("/api/case/{case_id}/report")
async def case_report(case_id: str):
    case = _get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return HTMLResponse(export.case_report_html(case))


@app.post("/api/vision/colors")
async def vision_colors(body: dict):
    """Extract dominant clothing colors from a base64 photo. Processed in memory,
    never stored. Colors only — no face/age/gender inference."""
    raw = (body.get("image") or "").strip()
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[-1]
    try:
        data = base64.b64decode(raw)
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "invalid image data")
    if not data:
        raise HTTPException(422, "no image provided")
    if len(data) > settings.MAX_IMAGE_BYTES:
        raise HTTPException(413, "image too large")
    try:
        colors = vision.extract_colors(data)
    except ValueError:
        raise HTTPException(422, "could not read that image")
    return {"colors": colors,
            "note": "Dominant colors detected in the photo (processed in memory, not stored). "
                    "Review before using — colors only, no identity inference."}


@app.post("/api/reverse")
async def reverse_search(body: dict, request: Request):
    """Match a reported sighting against known open cases (in-memory + persisted)."""
    _require_key(request)
    sighting = {k: (body.get(k) or "").strip()[: settings.MAX_FIELD_LEN]
                for k in ("location", "description", "clothing", "age")}
    if not sighting["location"] and not sighting["description"]:
        raise HTTPException(422, "provide at least a location or a description")
    cases: dict[str, dict] = {}
    for c in list(CASES.values()) + store.recent():
        if c.get("id"):
            cases.setdefault(c["id"], c)
    return {"matches": reverse.match_sighting(sighting, list(cases.values())), "checked": len(cases)}


# --- stateless variants (serverless mode keeps the case client-side) ---
@app.get("/api/authorities")
async def authorities_stateless(location: str = ""):
    return authorities.for_location(location)


@app.post("/api/chat")
async def chat_stateless(body: dict):
    case = body.get("case") or {}
    message = (body.get("message") or "").strip()[: settings.MAX_FIELD_LEN]
    if not message:
        raise HTTPException(422, "message required")
    answer = intel.chat_response(message, case)
    answer = await narrate.polish(answer, child=case.get("child"))
    return {"response": answer, "narrated": narrate.enabled()}


@app.post("/api/report")
async def report_stateless(body: dict):
    return HTMLResponse(export.case_report_html(body.get("case") or {}))


@app.get("/api/cctv")
async def cctv_stateless(lat: float, lng: float):
    return {"places": await places.nearby(lat, lng),
            "note": "Public places that commonly run CCTV near the point. Verify on the "
                    "ground and request any footage through the proper channel."}


@app.get("/api/health")
async def health():
    return {
        "status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION,
        "offline": settings.OFFLINE, "geocode": settings.GEOCODE_ENABLED,
        "persist": store.enabled(), "active_cases": len(CASES), "vision": True,
        "sync": settings.SYNC, "narrate": narrate.enabled(),
        "sources": [c["label"] for c in sources.CHANNELS],
    }


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/family")
async def family():
    """Calm, read-only family view (no raw-lead firehose, no chat/export)."""
    return FileResponse(STATIC / "family.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


# Demo presets live here (small, app-level) so sources.py is purely live adapters.
DEMO_CASES: dict[str, dict] = {
    "child": {
        "category": "child", "name": "Aarav Sharma", "age": "8", "photo_url": "",
        "last_seen_location": "Marina Beach, Chennai", "last_seen_time": "2026-06-19 17:30",
        "clothing": "red striped t-shirt, blue shorts",
        "distinguishing_features": "small scar above left eyebrow"},
    "dementia": {
        "category": "dementia", "name": "Rajan Iyer", "age": "72", "photo_url": "",
        "last_seen_location": "T. Nagar, Chennai", "last_seen_time": "2026-06-20 09:15",
        "clothing": "white veshti, grey shirt",
        "distinguishing_features": "wears a hearing aid, responds to 'Rajan', mild dementia"},
    "disaster": {
        "category": "disaster", "name": "Meena Kumari", "age": "34", "photo_url": "",
        "last_seen_location": "Chalakudy flood zone, Kerala", "last_seen_time": "2026-06-18 22:00",
        "clothing": "green saree", "distinguishing_features": "carrying an infant"},
    "tourist": {
        "category": "tourist", "name": "Lukas Weber", "age": "26", "photo_url": "",
        "last_seen_location": "Beach Road, Pondicherry", "last_seen_time": "2026-06-19 19:45",
        "clothing": "blue backpack, white cap",
        "distinguishing_features": "German national, limited Tamil/English"},
    "missing": {
        "category": "missing", "name": "Kavya Nair", "age": "19", "photo_url": "",
        "last_seen_location": "Chennai Central, Chennai", "last_seen_time": "2026-06-18 21:00",
        "clothing": "black kurta, blue jeans",
        "distinguishing_features": "left home without phone or wallet, no prior history"},
}
