"""
LifeLine — Missing Human Search Operations Console (open-source rebuild).

Search every wired *public* source at once and turn post-and-pray into one live,
ranked command center. No API keys, no credits, no black box: real free sources
(Google News, Bing News, GDELT, Reddit) + a fully deterministic intelligence layer.

Works for any missing human: child, dementia patient, disaster victim, lost tourist.

Run:  uvicorn app:app --reload --port 8000   ->  open http://localhost:8000
"""
from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import intel
import sources
from scoring import dedup, score_lead

app = FastAPI(title="LifeLine")

STATIC = Path(__file__).parent / "static"

# In-memory store. One process, one event — perfect for a live demo.
CASES: dict[str, dict] = {}


class ChildIn(BaseModel):
    category: str = "child"
    name: str
    age: str = ""
    photo_url: str = ""
    last_seen_location: str = ""
    last_seen_time: str = ""
    clothing: str = ""
    distinguishing_features: str = ""


async def run_search(case_id: str) -> None:
    """Background task: fan out across channels, score, stream leads into the case."""
    case = CASES[case_id]
    child = case["child"]
    started = time.perf_counter()

    # geocode the last-seen location so the Operations Map can drop a crosshair
    geo = sources.geocode(child.get("last_seen_location", ""))
    if geo:
        child["lat"], child["lng"], _ = geo

    # fan out across all channels CONCURRENTLY (live polls are slow one-by-one)
    async def run_channel(channel):
        scanned, raw = await sources.fetch_channel(channel, child)
        return channel, scanned, raw

    tasks = [asyncio.ensure_future(run_channel(ch)) for ch in sources.CHANNELS]
    for coro in asyncio.as_completed(tasks):
        channel, scanned, raw = await coro
        case["sources_searched"] += scanned
        accepted = 0
        for item in raw:
            lead = score_lead(item, case, channel["weight"])
            if any(l["url"] == lead["url"] for l in case["leads"]):
                continue
            case["leads"].append(lead)
            case["leads"] = dedup(case["leads"])
            accepted += 1
            await asyncio.sleep(0.18)  # stream effect: cards arrive one by one
        case["diagnostics"].append(
            {"channel": channel["label"], "query": sources.build_query(channel, child),
             "status": "done", "leads": accepted}
        )

    case["elapsed_s"] = round(time.perf_counter() - started, 1)
    case["done"] = True

    # Deterministic intelligence — no network, can't fail, fully explainable.
    case["intelligence"] = intel.analyze_case(case["leads"], case["child"])


@app.post("/api/search")
async def start_search(child: ChildIn):
    case_id = uuid.uuid4().hex[:8]
    CASES[case_id] = {
        "id": case_id,
        "child": child.model_dump(),
        "leads": [],
        "sources_searched": 0,
        "elapsed_s": 0.0,
        "done": False,
        "diagnostics": [],
        "intelligence": None,
    }
    asyncio.create_task(run_search(case_id))
    return {"case_id": case_id}


@app.get("/api/case/{case_id}")
async def get_case(case_id: str):
    case = CASES.get(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return case


@app.post("/api/case/{case_id}/lead/{lead_id}/status")
async def set_lead_status(case_id: str, lead_id: str, body: dict):
    case = CASES.get(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    status = body.get("status", "new")
    for lead in case["leads"]:
        if lead["id"] == lead_id:
            lead["status"] = status
            return {"ok": True}
    raise HTTPException(404, "lead not found")


@app.get("/api/categories")
async def categories():
    """The kinds of missing humans LifeLine can search for."""
    return sources.CATEGORIES


@app.get("/api/demo-case")
async def demo_case(category: str = "child"):
    """Pre-fill the intake form with the synthetic demo case for a category."""
    return sources.DEMO_CASES.get(category, sources.DEMO_CASES["child"])


@app.post("/api/case/{case_id}/chat")
async def chat(case_id: str, body: dict):
    case = CASES.get(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message required")
    return {"response": intel.chat_response(message, case)}


@app.post("/api/case/{case_id}/search-plan")
async def search_plan(case_id: str):
    case = CASES.get(case_id)
    if not case:
        raise HTTPException(404, "case not found")
    cmd = (case.get("intelligence") or {}).get("commander") or {}
    plan = intel.generate_search_plan(case["leads"], case["child"], cmd)
    if not plan:
        raise HTTPException(503, "no priority zones established yet")
    return plan


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
