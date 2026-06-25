# LifeFind — Missing Human Search Operations Console

**Find anyone — before it's too late. Every public source, one live command center.**

> We don't surveil people. Every sighting, news mention and public post already exists —
> it's just scattered. LifeFind unifies that public signal into one ranked, live command
> center in seconds instead of weeks. One engine, **any** missing human, **any** city.

The open-source rebuild of the *LifeLine* competition project — the Anakin Wire API and
Groq LLM ripped out, then hardened into something that actually ships.

### ✦ No keys. No credits. No black box.

| | Original (beacon) | LifeFind |
|---|---|---|
| Data | Anakin Wire API (credits, auth, 20s job-poll) | Google News · Bing · GDELT · Reddit — direct, free |
| Intelligence | Groq LLM (key, non-deterministic) | Deterministic engine — same numbers every run |
| Geography | hardcoded Chennai table | **any city on earth** (OpenStreetMap, cached) |
| Persistence | in-memory only | SQLite — cases survive restarts, **shareable by link** |
| Handoff | — | official channels + CSV / print-to-PDF dossier |
| API keys | `WIRE_API_KEY` + `GROQ_API_KEY` | **none** |
| Hardening | — | retries · rate-limit · validation · logging · 31 tests |

---

## Run it

```bash
cd lifeline
pip install -r requirements.txt
python -m uvicorn app:app --port 8000
```

Open **http://localhost:8000** → pick a category → **Begin Search Operation**.
No `.env`, no signup, nothing to configure.

```bash
LIFELINE_OFFLINE=1 python -m uvicorn app:app   # force the offline demo set (CI / no-wifi stage)
pytest -q                                        # 31 tests over the whole engine
```

---

## What makes it a difference-maker

- **Works anywhere** — type *Berlin*, *Tokyo*, *Cairo* or a Chennai neighbourhood; the
  map centers and leads plot correctly. Place names resolve via OpenStreetMap
  (cached, rate-limited to OSM policy) with an offline gazetteer fallback.
- **Shareable live cases** — every search has a URL (`/?case=<id>`). Send it to
  volunteers or police and they watch the same leads arrive in real time. Cases
  persist in SQLite.
- **Authority handoff** — LifeFind only aggregates *public* signal; it never replaces
  the authorities. It surfaces the right official channels for the case's region
  (Childline 1098, NCMEC, NamUs, Missing People, INTERPOL …) so the next click is a
  real report — plus one-click **CSV** and a **print-to-PDF dossier** to hand police a
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
| `scoring.py` | Deterministic, explainable scoring + de-dup |
| `store.py` | SQLite persistence (shareable cases) |
| `authorities.py` | Region → official channels |
| `export.py` | CSV + print-to-PDF dossier |
| `settings.py` | Env-driven configuration |
| `static/index.html` | Command center UI — no build step |
| `tests/` | 31 pytest cases |

### Deploying (Vercel)
Set `LIFELINE_DB=/tmp/lifefind.db` (serverless filesystems are read-only except `/tmp`).
Everything else works out of the box with no env at all.

---

*The original competition build lives on, frozen, as `beacon`. This is the version
that runs anywhere, for anyone, for free.*
