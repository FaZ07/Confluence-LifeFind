# LifeLine — Missing Human Search Operations Console

**Find anyone — before it's too late. Every public source, one live command center.**

> We don't surveil people. Every sighting, news mention and public post already exists —
> it's just scattered. LifeLine unifies that public signal into one ranked, live command
> center in seconds instead of weeks. One engine, **any** missing human.

This is the **open-source rebuild** of LifeLine. The original was wired to the Anakin
Wire API + Groq. This version rips both out: it talks to **real, free, public sources
directly** and runs a **fully deterministic** intelligence layer.

### ✦ No keys. No credits. No black box.

| | Original (beacon) | This rebuild |
|---|---|---|
| Data | Anakin Wire API (credits, auth, 20s job-poll) | Google News · Bing News · GDELT · Reddit — direct, free |
| Intelligence | Groq LLM (key, network, non-deterministic) | Deterministic engine — same numbers every run |
| API keys | `WIRE_API_KEY` + `GROQ_API_KEY` | **none** |
| Offline | manual `mock` toggle | automatic graceful fallback per channel |
| Tested | — | `pytest` over the whole engine |

---

## Not just children — any missing human

| Category | Example |
|----------|---------|
| 🧒 Missing child | the emotional lead-in |
| 🧓 Dementia / Alzheimer's | silver-alert wandering |
| 🌊 Disaster victim | floods, quakes, cyclones |
| 🧭 Lost tourist | foreign nationals, language barriers |
| 🔎 Missing person | the general case |

---

## Run it

```bash
cd lifeline
pip install -r requirements.txt
python -m uvicorn app:app --port 8000
```

Open **http://localhost:8000** → pick a category → **Begin Search Operation**.
No `.env`, no signup, nothing to configure.

Force the offline demo set (guaranteed-safe stage demo / CI):

```bash
LIFELINE_OFFLINE=1 python -m uvicorn app:app --port 8000
```

---

## The four real sources (`sources.py`)

Each channel is a **distinct, independent public engine** — not four queries to one API:

| Channel | Engine | Auth |
|---------|--------|------|
| News wire | Google News RSS | none |
| Local news | Bing News RSS | none |
| Global monitor | GDELT 2.0 Doc API (worldwide news monitor) | none |
| Sightings | Reddit search JSON | none |

Graceful, honest fallback per channel: if a source is blocked or rate-limited
(e.g. Reddit 403 from a datacenter IP, GDELT 429 under burst), the channel first
falls back to **real Google News** for its own angle — still live data — and only
drops to a bundled offline set on total network loss. So a live demo can never
hard-fail, and you never silently show canned data while you have internet.

---

## Deterministic intelligence (`intel.py`)

Everything the LLM used to do, computed straight from the scored leads:

- **Signal Fusion** — 2+ independent reports at the same named place fire a
  `⊕ SIGNAL FUSION` alert. Pure set arithmetic.
- **Priority Zones** — leads grouped by place, ranked by
  `total signal + corroboration + source diversity + specificity`, labelled HIGH/MEDIUM/LOW.
- **Auto Timeline** — chronological event log built from real lead dates.
- **Commander Chat** — intent-routed answers that quote the actual lead evidence
  ("why Marina Beach?" → cites the sources). Never fabricates.
- **Search Plan** — deterministic Alpha/Bravo/Charlie deployment order with a
  computed coverage estimate.

A judge can ask *"why is this the priority zone?"* and you point at the arithmetic.

---

## Scoring (`scoring.py`)

```
score =  source_weight * 30   (channel credibility)
       + location_match * 25   (mentions the last-seen place)
       + clothing_match * 20   (mentions what they were wearing)
       + recency        * 15   (how fresh)
       + name_match     * 10   (names the subject)
```

Every point on the confidence bar is explainable — the components add up exactly.

---

## Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI: search, case, chat, search-plan endpoints |
| `sources.py` | Four free public sources + geocoder + offline fallback |
| `intel.py` | Deterministic fusion, zones, timeline, chat, plan |
| `scoring.py` | Deterministic, explainable lead scoring + de-dup |
| `static/index.html` | Full command center UI — no build step |
| `tests/` | `pytest` over the deterministic engine |

```bash
pytest -q   # run the suite
```

---

*The original competition build lives on, frozen, as `beacon`. This is the version
that runs anywhere, forever, for free.*
