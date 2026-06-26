"""Reverse search — match a sighting against known open cases."""
import reverse


def _cases():
    return [
        {"id": "c1", "child": {"name": "Aarav Sharma", "age": "8",
                               "last_seen_location": "Marina Beach, Chennai",
                               "clothing": "red striped t-shirt", "distinguishing_features": "scar"}},
        {"id": "c2", "child": {"name": "Rajan Iyer", "age": "72",
                               "last_seen_location": "T. Nagar, Chennai",
                               "clothing": "white veshti", "distinguishing_features": "hearing aid"}},
    ]


def test_match_ranks_best_case_first():
    s = {"location": "Marina Beach Chennai", "description": "young boy",
         "clothing": "red striped shirt", "age": "8"}
    out = reverse.match_sighting(s, _cases())
    assert out and out[0]["case_id"] == "c1"
    assert out[0]["score"] >= 50


def test_location_and_age_drive_match():
    s = {"location": "T. Nagar Chennai", "description": "elderly man", "age": "72"}
    out = reverse.match_sighting(s, _cases())
    assert out and out[0]["case_id"] == "c2"


def test_unrelated_sighting_returns_no_credible_match():
    s = {"location": "London", "description": "man in a blue coat", "clothing": "blue coat", "age": "40"}
    out = reverse.match_sighting(s, _cases())
    assert all(m["score"] >= 20 for m in out)   # threshold enforced
    assert all(m["case_id"] for m in out)
