"""Test suite for static site generator (scripts/generate_site.py)."""

import json
from pathlib import Path
import pytest
from scripts.generate_site import build_site


def test_build_site_success(tmp_path: Path):
    openings_file = tmp_path / "openings.json"
    candidate_file = tmp_path / "candidate.json"
    output_html = tmp_path / "index.html"

    sample_openings = [
        {
            "id": "TEST-01",
            "company": "Airbus India",
            "title": "Lead MBSE Engineer",
            "location": "Bangalore",
            "req_id": "JR123",
            "fit_score": 5,
            "fit_rationale": "Perfect aerospace MBSE fit.",
            "skills_matched": ["MBSE", "Cameo", "SysML"],
            "apply_url": "https://ag.wd3.myworkdayjobs.com/test",
            "status": "Not Applied",
            "link_status": "active",
        }
    ]
    sample_candidate = {
        "name": "Mansi Agrawal",
        "current_title": "Lead Systems Engineer",
        "education": "MS Aerospace, Georgia Tech",
    }

    openings_file.write_text(json.dumps(sample_openings), encoding="utf-8")
    candidate_file.write_text(json.dumps(sample_candidate), encoding="utf-8")

    result = build_site(
        openings_path=openings_file,
        candidate_path=candidate_file,
        output_path=output_html,
    )

    assert result == output_html
    assert output_html.exists()
    content = output_html.read_text(encoding="utf-8")

    assert "Mansi Agrawal" in content
    assert "TEST-01" in content
    assert "https://ag.wd3.myworkdayjobs.com/test" in content
    assert "5★ Direct Fits" in content
    assert "Candidate Reference" in content
    assert "searchInput" in content
    assert "categoryFilter" in content
    assert "viewBtnTable" in content
