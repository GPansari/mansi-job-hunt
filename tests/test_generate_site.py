"""Test suite for static site generator (scripts/generate_site.py)."""

import json
from pathlib import Path
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
            "fit_rationale": "Strong aerospace MBSE fit.",
            "skills_matched": ["MBSE", "Cameo", "SysML"],
            "apply_url": "https://ag.wd3.myworkdayjobs.com/test",
            "url_type": "direct_requisition",
            "date_discovered": "2026-11-27",
            "status": "Not Applied",
            "link_status": "active",
        },
        {
            "id": "TEST-02",
            "company": "Green Aero Propulsion",
            "title": "Drone Engineer",
            "location": "Bengaluru",
            "req_id": "GA-1",
            "fit_score": 4,
            "fit_rationale": "UAV systems role.",
            "skills_matched": ["UAV"],
            "apply_url": "https://www.greenaero.in/careers/#roles",
            "url_type": "board_role_anchor",
            "date_discovered": "2026-11-26",
            "status": "Not Applied",
            "link_status": "active",
        },
        {
            "id": "TEST-INACTIVE",
            "company": "Old Corp",
            "title": "Expired Role",
            "location": "Bangalore",
            "req_id": "OLD-1",
            "fit_score": 5,
            "skills_matched": ["MBSE"],
            "apply_url": "https://example.com/old",
            "url_type": "direct_requisition",
            "date_discovered": "2026-09-22",
            "status": "Inactive Posting",
            "link_status": "expired",
        },
    ]
    sample_candidate = {
        "name": "Mansi Agrawal",
        "current_title": "Lead Systems Engineer",
        "experience_years": 10,
        "education": "MS Aerospace, Georgia Tech",
        "core_skills": ["MBSE", "SysML", "Cameo"],
        "target_titles": ["Lead Systems Engineer"],
        "target_domains": ["Commercial Aircraft", "UAV"],
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

    # Core elements & dynamic JSON embedding
    assert "Mansi Agrawal" in content
    assert "TEST-01" in content
    assert "https://ag.wd3.myworkdayjobs.com/test" in content
    assert "5★" in content
    assert "Direct Fit" not in content
    assert "Strong Fit" not in content
    assert "Candidate Reference" in content
    assert "searchInput" in content
    assert "categoryFilter" in content
    assert "viewBtnTable" in content

    # Phase 3 & 6 UX features
    assert "Posted" in content
    assert "sortSelect" in content
    assert "Recently Posted" in content
    assert "Fit + Posted" in content
    assert "Direct ATS" in content
    assert "Career Board Role" in content
    assert "populateCompanyFilter()" in content
    assert "renderCandidateDrawer()" in content
    assert "const CANDIDATE =" in content
    assert "const COMPANIES =" in content
    assert "tabBtnJobs" in content
    assert "tabBtnCompanies" in content
    assert "renderCompanies()" in content
    assert "formatLocation(" in content
    assert "let pageSize = 50;" in content
    assert "function escapeHtml(" in content
    assert "exportStatusesJson" not in content
    assert "importStatusesJson" not in content
    assert "localStorage" not in content
    assert "statusFilter" not in content
    assert "paginationBar" in content
    assert "toggleMobileFilters" in content
    # Accurate active/companies counts (2 active, 1 inactive excluded)
    assert 'id="kpi-active">2<' in content
    assert 'id="kpi-companies">2<' in content
