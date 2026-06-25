"""Deterministic scoring is the trust anchor — these lock the arithmetic."""
from scoring import _recency_score, dedup, score_lead


def _case():
    return {"child": {
        "name": "Aarav Sharma", "last_seen_location": "Marina Beach, Chennai",
        "clothing": "red striped t-shirt, blue shorts",
    }}


def test_breakdown_sums_to_score():
    raw = {"title": "Aarav Sharma missing near Marina Beach",
           "snippet": "wearing a red striped t-shirt", "url": "http://x/1", "date": "2026-06-20"}
    lead = score_lead(raw, _case(), source_weight=0.9)
    assert lead["match_score"] == sum(b["got"] for b in lead["breakdown"].values())
    assert 0 <= lead["match_score"] <= 100


def test_name_and_location_matches_register():
    raw = {"title": "Aarav Sharma seen at Marina Beach", "snippet": "", "url": "http://x/2", "date": "2026-06-20"}
    lead = score_lead(raw, _case(), source_weight=0.9)
    assert lead["breakdown"]["name"]["got"] == 10
    assert lead["breakdown"]["location"]["got"] > 0
    assert "Aarav Sharma" in lead["matched_attributes"]


def test_irrelevant_lead_scores_low():
    raw = {"title": "Cricket match in Mumbai", "snippet": "unrelated", "url": "http://x/3", "date": "2026-06-20"}
    lead = score_lead(raw, _case(), source_weight=0.62)
    assert lead["breakdown"]["name"]["got"] == 0
    assert lead["breakdown"]["location"]["got"] == 0


def test_recency_decays():
    assert _recency_score("2026-06-20") >= _recency_score("2026-05-20")
    assert _recency_score(None) == 0.5


def test_dedup_drops_same_url():
    leads = [
        {"url": "http://x/1", "title": "A boy missing", "match_score": 80},
        {"url": "http://x/1", "title": "A boy missing", "match_score": 60},
        {"url": "http://x/2", "title": "Different story entirely here", "match_score": 70},
    ]
    out = dedup(leads)
    assert len(out) == 2
    assert out[0]["match_score"] == 80  # highest kept first
