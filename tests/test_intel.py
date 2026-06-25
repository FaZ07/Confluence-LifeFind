"""The deterministic intelligence layer replaces the LLM — pin its behaviour."""
import intel


def _leads():
    # two specific-place leads at Marina Beach -> should fuse; one generic Chennai
    return [
        {"id": "a", "place": "Marina Beach", "match_score": 88, "date": "2026-06-20",
         "source_name": "The Hindu", "title": "Aarav missing near Marina Beach"},
        {"id": "b", "place": "Marina Beach", "match_score": 74, "date": "2026-06-19",
         "source_name": "Times of India", "title": "Family appeals for Aarav"},
        {"id": "c", "place": "Chennai", "match_score": 33, "date": "2026-06-10",
         "source_name": "r/india", "title": "unrelated chatter"},
    ]


def test_signal_fusion_needs_two_specific_sources():
    fusion = intel.compute_signal_fusion(_leads())
    assert fusion["top"]["location"] == "Marina Beach"
    assert fusion["top"]["source_count"] == 2
    assert "a" in fusion["by_lead"] and "c" not in fusion["by_lead"]


def test_commander_ranks_corroborated_zone_first():
    out = intel.analyze_case(_leads(), {"name": "Aarav Sharma"})
    zones = out["commander"]["priority_zones"]
    assert zones[0]["zone"] == "Marina Beach"
    assert zones[0]["confidence"] == "HIGH"
    assert "Marina Beach" in out["commander"]["recommended_action"]


def test_relevance_dims_weak_generic_lead():
    rel = intel.analyze_case(_leads(), {"name": "Aarav"})["relevance"]
    assert rel["a"] >= 8          # strong + specific
    assert rel["c"] < 4           # weak + generic -> UI drops it


def test_timeline_uses_real_lead_data():
    tl = intel.analyze_case(_leads(), {"name": "Aarav"})["timeline"]
    assert tl[0]["type"] == "zone"
    assert any(e["type"] == "lead" for e in tl)
    assert tl[-1]["type"] == "system"


def test_empty_case_is_safe():
    out = intel.analyze_case([], {"name": "X"})
    assert out["commander"] is None and out["timeline"] == []


def test_chat_explains_named_zone():
    case = {"child": {"name": "Aarav"}, "leads": _leads(),
            "intelligence": intel.analyze_case(_leads(), {"name": "Aarav"})}
    ans = intel.chat_response("why marina beach?", case)
    assert "Marina Beach" in ans
    assert "The Hindu" in ans  # cites the actual evidence


def test_chat_deploy_returns_plan():
    case = {"child": {"name": "Aarav"}, "leads": _leads(),
            "intelligence": intel.analyze_case(_leads(), {"name": "Aarav"})}
    ans = intel.chat_response("deploy teams", case)
    assert "Team Alpha" in ans and "coverage" in ans.lower()


def test_search_plan_is_deterministic():
    out = intel.analyze_case(_leads(), {"name": "Aarav"})
    plan = intel.generate_search_plan(_leads(), {"name": "Aarav"}, out["commander"])
    assert plan["teams"][0]["name"] == "Team Alpha"
    assert plan["teams"][0]["priority"] == "IMMEDIATE"
    assert plan["coverage_estimate"].endswith("%")
    # fully reproducible: same input -> identical output
    again = intel.generate_search_plan(_leads(), {"name": "Aarav"}, out["commander"])
    assert plan == again
