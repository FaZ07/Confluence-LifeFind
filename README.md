# LifeFind — the bridge between families searching and the officials who can act

[![CI](https://github.com/FaZ07/LifeFind/actions/workflows/ci.yml/badge.svg)](https://github.com/FaZ07/LifeFind/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Connecting the families who are searching with the officials who can act — by turning scattered public signal into one ranked, corroborated, official-ready case.**

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
| Hardening | — | retries · rate-limit · validation · logging · 90 tests |

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
pytest -q                                        # 90 tests over the whole engine
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
- **Reverse search & a family view** — flip it: a reported *sighting* is matched against
  the open cases LifeFind knows. And every case has a calm, read-only **family view**
  (status, what's been checked, most-mentioned areas) — no raw-lead firehose for an
  anxious family.
- **Only relevant leads** — results that match nothing about the subject are filtered as
  noise; the same story reworded across outlets is de-duplicated.

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

### Optional narration (`narrate.py`) — off by default

The engine decides everything — zones, scores, the assessment — deterministically,
**with or without an LLM**. If (and only if) you set a `GROQ_API_KEY`, the commander's
*chat replies* get rephrased into clearer prose. It is deliberately fenced in: it never
adds a fact or changes a number/decision, it **redacts the subject's identity before any
call** (no name, photo or address leaves the box), and it falls back to the deterministic
text on any error or when no key is set. No key → nothing here runs. The keyless,
auditable core stays the headline.

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

## Entity knowledge graph (`graph.py`)

The leads, drawn as a network: **sources** report **locations**, locations carry the
**clothing** corroborated there, and the **subject** anchors it. Node prominence is
normalized weighted-degree **network centrality**, and the standout — highlighted with a
glow — is the location the most *independent* sources converge on (the same hotspot the
fusion layer finds, now legible at a glance). Hover any node to trace its connections.
Fully deterministic: every node, edge and centrality value is computed straight from the
leads, so the picture is identical every run.

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

- **Time-aware statistical search radius (`searchmodel.py`)** — the empirical distance
  rings SAR teams use: given the point last seen and the subject category, the radii
  within which 50 / 75 / 95 % of comparable subjects have *historically* been found
  (published lost-person-behavior / ISRID data). **They now grow with time:** a person
  can't be farther than they could have travelled, so the area starts tight right after
  the disappearance and expands — bounded by an effective mobility horizon — until it
  saturates at the full historical distribution. The map shows the current area, the
  faint outer ring is where it will eventually reach, and **▶ Replay area growth**
  animates the whole expansion from t=0 to now. Still deterministic (same case + same
  elapsed time → same radii), **not** a prediction of the individual, and the speeds
  and radii are representative — calibrate to your region before operational use.
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
| `narrate.py` | Optional LLM narration — off without a key; never alters decisions |
| `analysis.py` | Corroboration, movement, clustering, search area, contradictions |
| `graph.py` | Entity knowledge graph — sources/places/clothing + network centrality |
| `vision.py` | Dominant clothing-color extraction from a photo (colors only) |
| `searchmodel.py` | Time-aware statistical search-radius rings (lost-person-behavior) |
| `places.py` | CCTV / footage-source discovery (OpenStreetMap) |
| `reverse.py` | Reverse search: sighting → match open cases |
| `scoring.py` | Deterministic, explainable scoring + de-dup + noise filter |
| `store.py` | SQLite persistence (shareable cases) |
| `authorities.py` | Region → official channels |
| `export.py` | CSV + printable case report |
| `settings.py` | Env-driven configuration |
| `static/index.html` | 4-page command center UI — no build step |
| `static/family.html` | Calm, read-only family view |
| `tests/` | 90 pytest cases (unit + API) |

### Demo vs Live data — a per-search toggle

The intake has a **Demo / Live** switch. *Demo* serves the bundled offline sample set
(instant, deterministic — great for a stage or no-wifi). *Live* hits the real public
sources (Google News · Bing · GDELT · Reddit) + global geocoding. It's a **per-request**
choice (`live` flag on `/api/search`), so it works on any deploy without an env change —
including the serverless demo. `LIFELINE_OFFLINE` only sets the *default* the switch
starts on (on by default on Vercel). Live mode is slower and, on a serverless host's short
function budget, can occasionally time out — that's the only catch.

### Deploying
LifeFind runs best as a long-lived process (live streaming + SQLite persistence), so for
the **full** feature set deploy it as a **stateful service** with a writable volume —
Docker, Fly.io, Render, Railway or a plain VM. Serverless (Vercel) runs a **demo mode**
(synchronous, no disk): live *data* still works via the toggle, but live streaming and
**shareable/persisted cases, the family view and reverse search are off** there — those
need the stateful deploy (a background task and shared store can't survive per-request
lambdas — no toggle changes that).

```bash
docker build -t lifefind .
docker run -p 8000:8000 -v lifefind-data:/data lifefind
```

No API keys required to run. Tune via env (see [`settings.py`](settings.py)):
`LIFELINE_DB`, `LIFELINE_CORS`, `LIFELINE_RATE_LIMIT_PER_MIN`, `LIFELINE_CASE_TTL_DAYS`,
`LIFELINE_API_KEY` (optional gate on case creation), `LIFELINE_MAX_ACTIVE_CASES`.

---

*The original competition build lives on, frozen, as `beacon`. This is the version
that runs anywhere, for anyone, for free.*
