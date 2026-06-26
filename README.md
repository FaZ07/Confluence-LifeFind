# LifeFind — Missing Human Search Operations Console

[![CI](https://github.com/FaZ07/LifeFind/actions/workflows/ci.yml/badge.svg)](https://github.com/FaZ07/LifeFind/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Public-signal triage that helps families, search teams and the authorities act faster.**

> We don't surveil people. Every sighting, news mention and public post already exists —
> it's just scattered. LifeFind unifies that public signal into one ranked, corroborated
> view in seconds instead of weeks. It assists the people already searching — it never
> replaces the police, and it always hands off to them.

The open-source rebuild of the *LifeLine* competition project — the Anakin Wire API and
Groq LLM ripped out, then hardened into something that actually ships.

### ✦ No keys. No credits. No black box.

| | Original (beacon) | LifeFind |
|---|---|---|
| Data | Anakin Wire API (credits, auth, 20s job-poll) | Google News · Bing · GDELT · Reddit — direct, free |
| Intelligence | Groq LLM (key, non-deterministic) | Deterministic engine — same numbers every run |
| Geography | hardcoded Chennai table | **any city on earth** (OpenStreetMap, cached) |
| Persistence | in-memory only | SQLite — cases survive restarts, **shareable by link** |
| Handoff | — | official channels + CSV / printable case report |
| API keys | `WIRE_API_KEY` + `GROQ_API_KEY` | **none** |
| Hardening | — | retries · rate-limit · validation · logging · 60 tests |

---

## Run it

```bash
cd lifeline
pip install -r requirements.txt
python -m uvicorn app:app --port 8000
```

Open **http://localhost:8000** → pick a category → **Start case**.
No `.env`, no signup, nothing to configure.

```bash
LIFELINE_OFFLINE=1 python -m uvicorn app:app   # force the offline demo set (CI / no-wifi stage)
pytest -q                                        # 60 tests over the whole engine
```

---

## What makes it a difference-maker

- **Works anywhere** — type *Berlin*, *Tokyo*, *Cairo* or a Chennai neighbourhood; the
  map centers and leads plot correctly. Place names resolve via OpenStreetMap
  (cached, rate-limited to OSM policy) with an offline gazetteer fallback.
- **Shareable live cases** — every search has a URL (`/?case=<id>`). Send it to
  police or a search team and they watch the same leads arrive in real time. Cases
  persist in SQLite.
- **Authority handoff** — LifeFind only aggregates *public* signal; it never replaces
  the authorities. It surfaces the right official channels for the case's region
  (Childline 1098, NCMEC, NamUs, Missing People, INTERPOL …) so the next click is a
  real report — plus one-click **CSV** and a **printable case report** to hand police a
  ranked lead package.

## The four real sources (`sources.py`)

| Channel | Engine | Auth |
|---------|--------|------|
| News wire | Google News RSS | none |
| Local news | Bing News RSS | none |
| Global monitor | GDELT 2.0 Doc API | none |
| Sightings | Reddit search JSON | none |

Graceful, honest fallback per channel: a blocked/rate-limited source falls back to
**real Google News** for its angle (still live data), and only drops to a bundled
offline set on total network loss — never silently canned while you have internet.

## Deterministic intelligence (`intel.py`)

Signal fusion · priority zones (HIGH/MED/LOW) · timeline · intent-routed commander
chat (quotes the actual evidence) · tactical search plan — every output computed
from the scored leads. A judge can ask *"why this zone?"* and you point at the
arithmetic.

## Investigation support (`analysis.py`)

Turns isolated clues into evidence — all deterministic, no ML:

- **Cross-source corroboration** — N independent sources agreeing on a place,
  clothing item or age, with the time window (*"4 sources reference Triplicane within 24h"*).
- **Report chronology** — the ordered sequence of *reported* locations (framed
  honestly as report order, not a claim the subject physically moved).
- **Geographic clustering** — weighted centre of activity + the radius covering
  ~80% of signal (*"75% within 2.9 km of Triplicane"*).
- **Search-area generation** — primary / secondary areas, transport hubs (derived
  from real reported places) and the movement corridor — drawn on the map.
- **Contradiction engine** — flags conflicting appearance descriptions across sources.

This is what takes it from a search *aggregator* to an *investigation-support* tool.

## Photo color analysis (`vision.py`)

Upload the missing person's photo → LifeFind extracts the **dominant clothing
colors** (unsupervised median-cut color clustering, center-weighted) and offers them
as one-tap chips that flow into the clothing field and the lead scoring. The image is
processed **in memory and never stored**.

**Colors only — no face recognition, no age/gender estimation, no identity matching.**
Inferring a person's age or gender from a single photo is bias-prone pseudo-science
and the kind of overclaim that discredits a serious system, so it is deliberately out.

## Operational search support

Two grounded aids for the people actually searching:

- **Statistical search radius (`searchmodel.py`)** — the empirical distance rings
  SAR teams use: given the point last seen and the subject category, the radii
  within which 50 / 75 / 95 % of comparable subjects have *historically* been found
  (published lost-person-behavior / ISRID data). Drawn on the map. It is **not** a
  prediction of the individual and **not** an AI guess — the figures are
  representative and must be calibrated to your region before operational use.
- **CCTV / footage-source discovery (`places.py`)** — the petrol bunks, ATMs,
  stations, banks and shops that commonly run CCTV within walking distance of the
  last-seen point (OpenStreetMap, free, no key). **Not** face recognition and
  **not** camera feeds — just the list of where to go request footage, so a search
  team doesn't burn time working it out on the ground.

## Scoring (`scoring.py`)

```
score = source_weight*30 + location_match*25 + clothing_match*20 + recency*15 + name_match*10
```

Every point on the confidence bar is explainable — the components add up exactly.

---

## Hardening

Input validation + field clamping · per-client rate limiting on search · retries with
backoff on every outbound call · structured logging · CORS · `/api/health` · graceful
degradation everywhere (read-only filesystem, blocked source, geocoder down — nothing
hard-fails). All config is env-driven (`settings.py`).

| File | Purpose |
|------|---------|
| `app.py` | FastAPI: search, case, chat, plan, authorities, export, health |
| `sources.py` | Four free public sources + retry/fallback |
| `geo.py` | Global geocoding (OSM) + offline gazetteer |
| `intel.py` | Deterministic fusion, zones, timeline, chat, plan |
| `analysis.py` | Corroboration, movement, clustering, search area, contradictions |
| `vision.py` | Dominant clothing-color extraction from a photo (colors only) |
| `searchmodel.py` | Statistical search-radius rings (lost-person-behavior) |
| `places.py` | CCTV / footage-source discovery (OpenStreetMap) |
| `scoring.py` | Deterministic, explainable scoring + de-dup |
| `store.py` | SQLite persistence (shareable cases) |
| `authorities.py` | Region → official channels |
| `export.py` | CSV + printable case report |
| `settings.py` | Env-driven configuration |
| `static/index.html` | Command center UI — no build step |
| `tests/` | 60 pytest cases (unit + API) |

### Deploying (Vercel)
Set `LIFELINE_DB=/tmp/lifefind.db` (serverless filesystems are read-only except `/tmp`).
Everything else works out of the box with no env at all.

---

*The original competition build lives on, frozen, as `beacon`. This is the version
that runs anywhere, for anyone, for free.*
