"""Export: CSV + printable case report for authority handoff."""
import export


def _case():
    return {
        "id": "case0001",
        "child": {"name": "Aarav Sharma", "category": "child", "age": "8",
                  "last_seen_location": "Marina Beach, Chennai", "clothing": "red shirt",
                  "last_seen_time": "2026-06-19 17:30", "distinguishing_features": "scar"},
        "leads": [
            {"match_score": 88, "source_name": "The Hindu", "title": "Aarav missing near Marina",
             "date": "2026-06-20", "place": "Marina Beach", "status": "new", "url": "http://x/1"},
            {"match_score": 60, "source_name": "r/Chennai", "title": "possible sighting",
             "date": "2026-06-20", "place": "Triplicane", "status": "reviewing", "url": "http://x/2"},
        ],
        "intelligence": {"commander": {"priority_zones": [
            {"zone": "Marina Beach", "confidence": "HIGH", "reason": "2 reports"}]}},
    }


def test_csv_has_header_and_rows():
    csv = export.leads_csv(_case())
    lines = [l for l in csv.splitlines() if l.strip()]
    assert lines[0].startswith("rank,match_score,source")
    assert len(lines) == 3                       # header + 2 leads
    assert "The Hindu" in csv and "88" in csv     # highest score ranked first


def test_csv_ranks_by_score():
    rows = export.leads_csv(_case()).splitlines()
    assert rows[1].startswith("1,88")            # top lead first


def test_case_report_html_is_well_formed():
    html = export.case_report_html(_case())
    assert "<html" in html and "MISSING" in html
    assert "Aarav Sharma" in html
    assert "Marina Beach" in html                # priority zone rendered
    assert "Triplicane" in html                  # lead rendered
