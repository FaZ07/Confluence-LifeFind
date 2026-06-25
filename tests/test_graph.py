"""Deterministic entity knowledge graph."""
import graph


def _case():
    return {
        "child": {"name": "Aarav Sharma", "category": "child", "clothing": "red shirt, blue shorts"},
        "leads": [
            {"id": "a", "place": "Marina Beach", "source_name": "The Hindu", "source_type": "news",
             "match_score": 88, "title": "Aarav seen at Marina Beach in red shirt", "snippet": ""},
            {"id": "b", "place": "Marina Beach", "source_name": "Times of India", "source_type": "news",
             "match_score": 74, "title": "red shirt boy spotted near Marina Beach", "snippet": ""},
            {"id": "c", "place": "Triplicane", "source_name": "r/Chennai", "source_type": "social",
             "match_score": 40, "title": "possible sighting", "snippet": ""},
        ],
    }


def test_builds_subject_place_source_and_clothing_nodes():
    g = graph.build_graph(_case())
    types = {n["type"] for n in g["nodes"]}
    assert {"subject", "place", "source"} <= types
    assert any(n["type"] == "clothing" and n["label"] == "red shirt" for n in g["nodes"])  # detected in text
    assert not any(n["label"] == "blue shorts" for n in g["nodes"])    # never mentioned -> no node
    assert len(g["edges"]) > 0


def test_central_is_the_most_corroborated_place():
    g = graph.build_graph(_case())
    assert g["central"]["label"] == "Marina Beach"   # 2 independent sources beat 1
    assert g["central"]["sources"] == 2


def test_centrality_is_normalized():
    g = graph.build_graph(_case())
    assert all(0.0 <= n.get("centrality", 0) <= 1.0 for n in g["nodes"])
    # the central place should out-rank the lone Triplicane lead
    cen = {n["label"]: n.get("centrality", 0) for n in g["nodes"] if n["type"] == "place"}
    assert cen["Marina Beach"] > cen["Triplicane"]


def test_is_deterministic():
    assert graph.build_graph(_case()) == graph.build_graph(_case())


def test_empty_case_returns_none():
    assert graph.build_graph({"child": {}, "leads": []}) is None
    assert graph.build_graph({"child": {}, "leads": [{"id": "x", "source_name": "s"}]}) is None  # no place
