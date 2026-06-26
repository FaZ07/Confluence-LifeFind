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
import time
import uuid
from contextlib import asynccontextmanager
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


def _get_case(case_id: str) -> dict | None:
    """Live in-memory case if present, else a persisted snapshot, else None."""
    return CASES.get(case_id) or store.load(case_id)


async def run_search(case_id: str) -> None:
    """Background task: geocode, fan out across channels, score, persist."""
    case = CASES[case_id]
    child = case["child"]
    started = time.perf_counter()

    # Global geocoding: resolve the case location (any city on earth) + a gazetteer.
    gaz = await geo.build_gazetteer(child.get("last_seen_location", ""))
    center = gaz.get("center")
    if center:
        child["lat"], child["lng"], child["place"] = center
    case["geocoded"] = center is not None
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
            if any(l["url"] == lead["url"] for l in case["leads"]):
                continue
            case["leads"].append(lead)
            case["leads"] = dedup(case["leads"])
            accepted += 1
            await asyncio.sleep(0.18)                  # stream effect
        case["diagnostics"].append(
            {"channel": channel["label"], "query": sources.build_query(channel, child),
             "status": "done", "leads": accepted})
        store.save(case)

    case["elapsed_s"] = round(time.perf_counter() - started, 1)
    case["done"] = True

    # Deterministic intelligence — only the case's resolved CITY is treated as
    # city-level (so the specific last-seen spot still fuses normally).
    generics = {gaz["city"]} if gaz.get("city") else set()
    case["intelligence"] = intel.analyze_case(case["leads"], case["child"], generics)
    store.save(case)
    log.info("case %s complete: %d leads, %.1fs", case_id, len(case["leads"]), case["elapsed_s"])


@app.post("/api/search")
async def start_search(child: ChildIn, request: Request):
    client = request.client.host if request.client else "anon"
    if not _rate_ok(client):
        raise HTTPException(429, "rate limit exceeded — slow down a moment")
    if not child.name and not child.last_seen_location:
        raise HTTPException(422, "provide at least a name or a last-seen location")
    if child.category not in {c["key"] for c in sources.CATEGORIES}:
        child.category = "missing"

    case_id = uuid.uuid4().hex[:8]
    CASES[case_id] = {
        "id": case_id, "child": child.model_dump(), "leads": [],
        "sources_searched": 0, "elapsed_s": 0.0, "done": False,
        "geocoded": False, "diagnostics": [], "intelligence": None,
    }
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


@app.get("/api/demo-case")
async def demo_case(category: str = "child"):
    return DEMO_CASES.get(category, DEMO_CASES["child"])


@app.post("/api/case/{case_id}/chat")
async def chat(case_id: str, body: dict):
    case = _get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    message = (body.get("message") or "").strip()[: settings.MAX_FIELD_LEN]
    if not message:
        raise HTTPException(422, "message required")
    return {"response": intel.chat_response(message, case)}


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


@app.get("/api/case/{case_id}/export.csv")
async def export_csv(case_id: str):
    case = _get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return PlainTextResponse(
        export.leads_csv(case), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="lifefind-{case_id}.csv"'})


@app.get("/api/case/{case_id}/dossier")
async def dossier(case_id: str):
    case = _get_case(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return HTMLResponse(export.dossier_html(case))


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


@app.get("/api/health")
async def health():
    return {
        "status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION,
        "offline": settings.OFFLINE, "geocode": settings.GEOCODE_ENABLED,
        "persist": store.enabled(), "active_cases": len(CASES), "vision": True,
        "sources": [c["label"] for c in sources.CHANNELS],
    }


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


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
