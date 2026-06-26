# LifeFind — the bridge between families searching and the officials who can act

[![CI](https://github.com/FaZ07/LifeFind/actions/workflows/ci.yml/badge.svg)](https://github.com/FaZ07/LifeFind/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![No API keys](https://img.shields.io/badge/API_keys-none-success)
![Tests](https://img.shields.io/badge/tests-90_passing-success)

> When someone goes missing, the information that could find them **already exists** — a
> neighbour's post, a local news mention, a sighting on Reddit, a global news monitor — but
> it's scattered across the internet, and across the gap between a frightened **family** and an
> overstretched **official**. In those first hours, that gap costs lives.
>
> **LifeFind closes the gap.** A family reports once; LifeFind fuses scattered *public* signal
> into one ranked, corroborated, **auditable, official-ready case**; and hands it to the
> authorities who can act.

```
   👪  Family reports   ──►   ◈  LifeFind corroborates public signal   ──►   🛡️  Officials act
   one form, any city       deterministic fusion · provenance · audit        ranked, sourced case
```

**🔗 Live demo:** https://lifeline-alpha-two.vercel.app · **No API keys. No accounts. Runs anywhere, free.**

---

## 🎯 The problem

Missing-person searches are won or lost in the first hours, yet the relevant information is
**fragmented** and **untrusted**:

- A **family** has scraps — a Facebook plea, a blurry photo, three different spellings of a place —
  and no way to know which scrap is a real lead.
- **Officials** receive a flood of well-meaning but unverified tips and have to triage by hand.
- Nobody has a single, **trustworthy, traceable** view that both sides can act on.

LifeFind is the connective tissue: it turns a family's scattered worry into a structured case an
official can defend in a report — **without surveilling anyone**. Every signal it uses is already
public; it just unifies, ranks, and shows its work.

---

## ✅ What it does — the working prototype (end to end)

Every step below runs today, locally and on the live URL:

1. **Family intake** — pick a category (child · dementia · disaster · tourist · missing adult),
   describe the person, and choose the last-seen location from a **live city autocomplete**
   (OpenStreetMap — any city on earth, no key).
2. **Cinematic AI reasoning** — launch the case and *watch the engine think*: it streams its
   real pipeline steps (located → fanned across sources → scored → fused → built the entity
   network → ranked zones) so the intelligence is **legible, not a black box**.
3. **Live operations map** — leads stream onto a Leaflet map as density, with priority zones and
   a **time-aware search radius** that grows with the minutes elapsed.
4. **Intelligence** — deterministic **priority zones**, cross-source **corroboration**, a
   **timeline**, and a **living entity graph** (the ontology) you can click to ask *"why is this
   node here?"* — answered with the exact sources that produced it.
5. **Triage (the decision layer)** — every lead gets **Verify / Escalate / Dismiss** (human in the
   loop), a **provenance** panel (the exact deterministic score breakdown + the source URL), and
   **entity resolution** (fuzzy-matched duplicate places you can **Merge** — which re-fuses the
   graph live).
6. **Tamper-evident audit trail** — every analyst action is written to an **append-only,
   SHA-256 hash-chained** log with a live *"chain verified"* badge. Court-grade provenance.
7. **CCTV footage sources** — real public places likely to run CCTV near the last-seen point
   (where to *request* footage — not feeds, not face recognition), with a worked/requested status
   you can track.
8. **Handoff** — one click to the right **official channels** for the region (Police 100, Childline,
   NCMEC, NamUs, INTERPOL…), a **shareable operational link**, a calm **family view**, a **CSV**,
   and a **printable case report**.

---

## 🏅 How this maps to the judging criteria

| Criterion | Where to look | Evidence |
|---|---|---|
| **Core Prototype Functionality** | The 8-step flow above, live | Full path works end to end on the live URL; **90 automated tests** pass; a case can never wedge (every search reaches a valid terminal state). |
| **Technical Foundation** | `app.py`, `intel.py`, `audit.py`, `graph.py` | Async FastAPI fan-out across 4 real sources; a **fully deterministic** intelligence engine (same input → same output, auditable); a **hash-chained audit log**; **zero API keys / zero infra** to run; SQLite persistence; ruff-clean; CI on every push. |
| **Problem-Solution Alignment** | Intake → Handoff, `authorities.py`, `family.html` | It is *literally* the bridge: a family reports, the engine corroborates **public** signal, and it hands a ranked, sourced package to the authorities — with a separate calm family view. Honest by design (public signal only; **not** face recognition). |
| **UX & Usability** | The whole UI (`static/index.html`) | A clean dashboard with a guided, sequential nav; **city autocomplete** so locations resolve correctly worldwide; tooltips on every action; the cinematic loader makes the AI **understandable in 5 seconds**; keyboard-focusable, responsive. |
| **Progress & Demo Clarity** | Demo script below | The reasoning stream narrates exactly what's happening; the **"Why" panel** and **audit trail** let a judge interrogate any conclusion; a tight 2-minute script lands the wow + the substance. |

---

## 🧱 Tech stack

| Layer | Choice |
|---|---|
| **Backend** | Python 3.12 · **FastAPI** · Uvicorn · **Pydantic v2** (input hardening) · **httpx** (async, retries) |
| **Intelligence** | **Fully deterministic** Python (fusion, zones, scoring, graph, search-radius) — no ML black box in the decision path |
| **Integrity** | stdlib `hashlib` (SHA-256 audit chain) · `secrets` (unguessable case IDs) · `contextvars` (per-request Demo/Live) |
| **Data (all free, no auth)** | Google News RSS · Bing News RSS · **GDELT 2.0** · Reddit JSON · **OpenStreetMap** (geocode + footage sources) |
| **Vision** | **Pillow** — dominant clothing-colour extraction (colours only; no face/age/gender inference) |
| **Persistence** | **SQLite** (cases + audit) · `localStorage` (client workflow) |
| **Frontend** | **Vanilla HTML/CSS/JS — no build step** · **Leaflet** maps · custom **SVG** entity graph |
| **Optional** | Groq LLM — *only* rephrases chat replies, off by default, redacts identity, never decides |
| **Quality** | **pytest (90)** · ruff · GitHub Actions CI · Docker |

> **The headline engineering decision:** the entire intelligence layer is **deterministic and keyless**.
> A judge can point at any zone, score, or link and ask *"why?"* — and the answer is arithmetic on
> public data, reproducible every run. That is what makes it defensible, not just impressive.

---

## 🗺️ Architecture & module map

```
Intake (Demo│Live) ─► POST /api/search ─► run_search():
    geo.build_gazetteer ─► searchmodel.rings
    asyncio fan-out over sources.CHANNELS ─► geo.locate_lead ─► scoring.score_lead ─► dedup/on_topic
    intel.analyze_case (fusion · zones · timeline · commander) ─► graph.build_graph
    store.save (SQLite)            ▲ streamed to the UI as it arrives
Frontend polls /api/case/{id} ─► cinematic reasoning loader ─► dashboard
Analyst acts ─► POST status/audit ─► audit.append (SHA-256 chained)
```

| Module | Responsibility |
|---|---|
| `app.py` | FastAPI surface, background search pipeline, rate limiting, demo cases |
| `settings.py` | Env-driven config; Demo/Live ContextVar; serverless vs stateful modes |
| `sources.py` | The 4 real public-source adapters + per-channel graceful fallback |
| `geo.py` | Global geocoding + **city autocomplete** (`/api/geocode`) + offline gazetteer |
| `scoring.py` | Deterministic, explainable score + de-dup + noise filter |
| `intel.py` | Fusion, priority zones, timeline, intent-routed commander chat, search plan |
| `analysis.py` | Corroboration, chronology, clustering, search-area, contradictions |
| `graph.py` | The **ontology** — entity network + centrality |
| `searchmodel.py` | Time-aware statistical search-radius rings (ISRID lost-person-behaviour) |
| `places.py` | CCTV / footage-source discovery (OpenStreetMap) |
| `vision.py` | Dominant clothing-colour extraction (colours only) |
| `reverse.py` | Reverse search — match a sighting to open cases |
| `store.py` | SQLite persistence (shareable cases) |
| `authorities.py` | Region → official channels |
| `export.py` | CSV + printable case report |
| `audit.py` | **Append-only, hash-chained audit trail** |
| `narrate.py` | Optional LLM rephrase (off by default, never decides) |
| `static/index.html` | The full single-file SPA + cinematic loader + living graph |
| `static/family.html` | Calm, read-only family view |
| `tests/` | 90 pytest cases (unit + API) |

---

## ▶️ Run it (30 seconds, no setup)

```bash
cd lifeline
pip install -r requirements.txt
python -m uvicorn app:app --port 8000
# open http://localhost:8000  →  pick a category  →  Start case
```

No `.env`, no signup, nothing to configure.

```bash
LIFELINE_OFFLINE=1 python -m uvicorn app:app   # instant bundled demo (stage / no-wifi)
pytest -q                                       # 90 tests over the whole engine
docker build -t lifefind . && docker run -p 8000:8000 -v lifefind-data:/data lifefind
```

> **Demo vs Live:** the intake has a green **Demo / Live** switch. *Demo* serves an instant bundled
> sample (great on stage); *Live* hits the real public sources for **any city you type**. For real
> results, flip it to **Live**.

---

## 🎬 2-minute demo script (for the pitch)

1. **(0:00)** "Someone's child is missing in Jaipur." Type *Jaipur* → **pick it from the live
   autocomplete** → Start case.
2. **(0:15)** Let the **AI reasoning loader** play — narrate: *"it's not a black box; it's showing
   you exactly how it reasons."*
3. **(0:40)** Land on the **map** — priority zone + growing search radius.
4. **(1:00)** **Intelligence** → click the brightest node in the **entity graph** → the **"Why"
   panel**: *"this place was corroborated by 3 independent sources."* Open **Schema** to show the
   ontology.
5. **(1:25)** **Triage** → **Verify** a lead → watch its node turn green on the graph **live** →
   open the **audit trail**: *"chain verified — every action is tamper-evident."*
6. **(1:50)** **Handoff** → "one click and the official has Police 100, a shareable link, and a
   printable case report." **The bridge is complete.**

---

## 🛡️ Design principles & ethics (why it's defensible)

- **Deterministic, not a guess.** Zones, scores and links are arithmetic on public data —
  reproducible and explainable. The optional LLM only rephrases; it never decides.
- **Public signal only.** Everything it reads is already public. It **never** does face
  recognition, age/gender inference, or camera-feed ingest — and says so.
- **Human in the loop.** Nothing is "active" until a person verifies it; every decision is logged.
- **Provenance & audit.** Tamper-evident hash chain; every lead traces to its source URL.
- **Privacy.** Unguessable case links, access-time expiry, photos processed in memory and never
  stored, identity redacted before any optional LLM call.

---

## 🚀 Roadmap

- **Competing-hypotheses analyzer** — *voluntary disappearance* vs *abduction*, each with its own
  auto-assembled evidence chain and deterministic confidence.
- Persistent audit on a stateful host (Render / Fly / Railway) — full chain survives restarts.
- Cross-case **person** entity resolution (variant-name matching across cases).

---

*Built to be honest, auditable, and genuinely useful — the version that runs anywhere, for anyone,
for free. MIT licensed.*
