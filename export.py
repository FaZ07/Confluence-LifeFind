"""
LifeFind — export. Turn a live case into something you can hand to the authorities:
a ranked CSV of leads, and a clean print-to-PDF dossier. Stdlib only.
"""
from __future__ import annotations

import csv
import html
import io
from datetime import datetime, timezone


def leads_csv(case: dict) -> str:
    leads = sorted(case.get("leads", []), key=lambda l: -l.get("match_score", 0))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "match_score", "source", "title", "date", "place", "status", "url"])
    for i, l in enumerate(leads, 1):
        w.writerow([
            i, l.get("match_score", 0), l.get("source_name", ""), l.get("title", ""),
            l.get("date", ""), l.get("place", ""), l.get("status", "new"), l.get("url", ""),
        ])
    return buf.getvalue()


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def dossier_html(case: dict) -> str:
    child = case.get("child", {})
    leads = sorted(case.get("leads", []), key=lambda l: -l.get("match_score", 0))
    intel = case.get("intelligence") or {}
    cmd = intel.get("commander") or {}
    zones = cmd.get("priority_zones") or []
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    zone_rows = "".join(
        f"<tr><td>{i+1}</td><td>{_esc(z.get('zone'))}</td>"
        f"<td>{_esc(z.get('confidence'))}</td><td>{_esc(z.get('reason'))}</td></tr>"
        for i, z in enumerate(zones)
    ) or "<tr><td colspan=4>No priority zones established.</td></tr>"

    lead_rows = "".join(
        f"<tr><td>{i+1}</td><td>{l.get('match_score', 0)}</td><td>{_esc(l.get('source_name'))}</td>"
        f"<td>{_esc(l.get('title'))}</td><td>{_esc(l.get('place'))}</td><td>{_esc(l.get('date'))}</td>"
        f"<td><a href='{_esc(l.get('url'))}'>link</a></td></tr>"
        for i, l in enumerate(leads)
    ) or "<tr><td colspan=7>No leads.</td></tr>"

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>LifeFind dossier — {_esc(child.get('name', 'case'))}</title>
<style>
  body{{font-family:Arial,Helvetica,sans-serif;color:#111;max-width:900px;margin:24px auto;padding:0 18px}}
  h1{{margin:0 0 2px}} .sub{{color:#555;margin:0 0 18px;font-size:13px}}
  .grid{{display:grid;grid-template-columns:1fr 1fr;gap:6px 24px;font-size:14px;margin-bottom:18px}}
  .k{{color:#666;font-size:11px;text-transform:uppercase;letter-spacing:.5px}}
  table{{width:100%;border-collapse:collapse;margin:8px 0 22px;font-size:12.5px}}
  th,td{{text-align:left;border-bottom:1px solid #ddd;padding:6px 8px;vertical-align:top}}
  th{{background:#f4f4f4}} .banner{{background:#fff7e6;border:1px solid #ffd591;padding:10px 12px;border-radius:6px;font-size:12px;margin-bottom:18px}}
  @media print{{ a{{color:#111;text-decoration:none}} }}
</style></head><body>
<h1>MISSING — {_esc(child.get('name', 'Unknown'))}</h1>
<p class="sub">LifeFind search dossier · generated {generated} · case {_esc(case.get('id'))}</p>
<div class="banner">This dossier compiles <b>public</b> news, records and community reports.
It is decision-support for searchers and authorities — not a substitute for an official investigation.</div>
<div class="grid">
  <div><div class="k">Category</div>{_esc(child.get('category'))}</div>
  <div><div class="k">Age</div>{_esc(child.get('age'))}</div>
  <div><div class="k">Last seen</div>{_esc(child.get('last_seen_location'))}</div>
  <div><div class="k">Last seen time</div>{_esc(child.get('last_seen_time'))}</div>
  <div><div class="k">Clothing</div>{_esc(child.get('clothing'))}</div>
  <div><div class="k">Distinguishing</div>{_esc(child.get('distinguishing_features'))}</div>
</div>
<h3>Priority zones</h3>
<table><tr><th>#</th><th>Zone</th><th>Confidence</th><th>Why</th></tr>{zone_rows}</table>
<h3>Leads ({len(leads)}) — ranked by match score</h3>
<table><tr><th>#</th><th>Score</th><th>Source</th><th>Title</th><th>Place</th><th>Date</th><th>Link</th></tr>{lead_rows}</table>
</body></html>"""
