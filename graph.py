"""
LifeFind — entity knowledge graph (deterministic, no ML).

Turns the scored leads into a network of *who said what, where*:

    SOURCE  --reports-->  PLACE  --corroborates-->  CLOTHING
                            ^
                          SUBJECT (anchor)

Node prominence is normalized weighted-degree centrality; the standout is the place
the most INDEPENDENT sources converge on — the same hotspot the signal-fusion layer
finds, now drawn as a graph you can read at a glance. Every node, edge and centrality
value is computed straight from the leads, so the picture is identical every run.
"""
from __future__ import annotations

import re

_MAX_PLACES = 8
_MAX_SOURCES = 10
_MAX_CLOTH = 6


def _clothing_terms(child: dict) -> list[str]:
    return [p.strip() for p in re.split(r"[,]", (child or {}).get("clothing", "")) if p.strip()]


def build_graph(case: dict) -> dict | None:
    """Build the entity network for a case, or None if there's nothing to draw."""
    leads = [l for l in case.get("leads", []) if l.get("place")]
    child = case.get("child", {}) or {}
    if not leads:
        return None

    cloth_lower = {c.lower(): c for c in _clothing_terms(child)}

    places: dict[str, dict] = {}      # place -> {sources:set, weight, leads}
    sources: dict[str, dict] = {}     # source -> {places:set, weight, type, leads}
    edge_sp: dict[tuple, int] = {}    # (source, place) -> summed match_score
    edge_pc: dict[tuple, int] = {}    # (place, clothing) -> count

    for l in leads:
        p = l["place"]
        s = l.get("source_name", "source")
        w = l.get("match_score", 0)
        pl = places.setdefault(p, {"sources": set(), "weight": 0, "leads": 0})
        pl["sources"].add(s); pl["weight"] += w; pl["leads"] += 1
        sr = sources.setdefault(s, {"places": set(), "weight": 0, "type": l.get("source_type", "web"), "leads": 0})
        sr["places"].add(p); sr["weight"] += w; sr["leads"] += 1
        edge_sp[(s, p)] = edge_sp.get((s, p), 0) + w
        text = f"{l.get('title', '')} {l.get('snippet', '')}".lower()
        for cl_lower, cl in cloth_lower.items():
            if cl_lower in text:
                edge_pc[(p, cl)] = edge_pc.get((p, cl), 0) + 1

    # keep the strongest places/sources so the picture stays legible (ties: insertion order)
    top_places = sorted(places, key=lambda p: (len(places[p]["sources"]), places[p]["weight"]), reverse=True)[:_MAX_PLACES]
    top_sources = sorted(sources, key=lambda s: (sources[s]["weight"], len(sources[s]["places"])), reverse=True)[:_MAX_SOURCES]
    tp, ts = set(top_places), set(top_sources)
    used_cloth: list[str] = []
    for (p, cl) in edge_pc:
        if p in tp and cl not in used_cloth:
            used_cloth.append(cl)
    used_cloth = used_cloth[:_MAX_CLOTH]
    uc = set(used_cloth)

    nodes: list[dict] = [{
        "id": "subject", "label": child.get("name") or "Subject", "type": "subject",
        "centrality": 1.0, "category": child.get("category", ""),
    }]
    for p in top_places:
        nodes.append({"id": "place:" + p, "label": p, "type": "place",
                      "sources": len(places[p]["sources"]), "leads": places[p]["leads"],
                      "weight": places[p]["weight"]})
    for s in top_sources:
        nodes.append({"id": "source:" + s, "label": s, "type": "source",
                      "source_type": sources[s]["type"], "places": len(sources[s]["places"]),
                      "weight": sources[s]["weight"]})
    for cl in used_cloth:
        nodes.append({"id": "cloth:" + cl, "label": cl, "type": "clothing"})

    edges: list[dict] = []
    for (s, p), w in edge_sp.items():
        if s in ts and p in tp:
            edges.append({"source": "source:" + s, "target": "place:" + p, "weight": w, "rel": "reports"})
    for (p, cl), c in edge_pc.items():
        if p in tp and cl in uc:
            edges.append({"source": "place:" + p, "target": "cloth:" + cl, "weight": c * 10, "rel": "corroborates"})
    for cl in used_cloth:
        edges.append({"source": "subject", "target": "cloth:" + cl, "weight": 5, "rel": "wearing"})
    if top_places:
        edges.append({"source": "subject", "target": "place:" + top_places[0], "weight": 8, "rel": "last seen near"})

    # centrality = normalized weighted degree (subject pinned at 1.0 as the anchor)
    deg: dict[str, int] = {}
    for e in edges:
        deg[e["source"]] = deg.get(e["source"], 0) + e["weight"]
        deg[e["target"]] = deg.get(e["target"], 0) + e["weight"]
    maxdeg = max(deg.values()) if deg else 1
    for n in nodes:
        if n["type"] != "subject":
            n["centrality"] = round(deg.get(n["id"], 0) / maxdeg, 3)

    central = None
    if top_places:
        best = max(top_places, key=lambda p: (len(places[p]["sources"]), places[p]["weight"]))
        central = {"id": "place:" + best, "label": best,
                   "sources": len(places[best]["sources"]), "leads": places[best]["leads"]}

    return {
        "nodes": nodes, "edges": edges, "central": central,
        "stats": {"places": len(places), "sources": len(sources),
                  "shown_nodes": len(nodes), "shown_edges": len(edges)},
    }
