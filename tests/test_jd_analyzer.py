import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.jd_analyzer import (
    analyze_jd,
    fetch_jd_text,
    load_opening_by_id,
    main,
    save_analysis,
)
from scripts.profile_loader import load_master_profile


def test_fetch_jd_text_blocks_linkedin_urls():
    with pytest.raises(ValueError, match="LinkedIn"):
        fetch_jd_text("https://www.linkedin.com/jobs/view/1234567890")


def test_fetch_jd_text_blocks_regional_linkedin_subdomains():
    with pytest.raises(ValueError, match="LinkedIn"):
        fetch_jd_text("https://in.linkedin.com/jobs/view/987654321")


def test_fetch_jd_text_strips_html_scripts_and_styles(monkeypatch):
    html_body = """
    <html>
      <head>
        <title>Job</title>
        <style>.hidden { display: none; }</style>
        <script>window.__INITIAL_STATE__ = {"secret": 1};</script>
      </head>
      <body>
        <h1>Lead Systems Engineer</h1>
        <p>Requirements: <strong>MBSE</strong>, SysML &amp; ARP4754A.</p>
        <ul>
          <li>Cameo Systems Modeler</li>
          <li>IBM DOORS</li>
        </ul>
      </body>
    </html>
    """

    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "text/html; charset=utf-8"}
        text = html_body

        def raise_for_status(self):
            return None

    called = {}

    def fake_get(url, headers=None, timeout=None):
        called["url"] = url
        called["headers"] = headers
        called["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("scripts.jd_analyzer.requests.get", fake_get)

    text = fetch_jd_text("https://boards.greenhouse.io/acme/jobs/123", timeout=10)
    assert called["url"] == "https://boards.greenhouse.io/acme/jobs/123"
    assert called["timeout"] == 10
    assert "User-Agent" in called["headers"]
    assert "Lead Systems Engineer" in text
    assert "MBSE, SysML & ARP4754A." in text
    assert "Cameo Systems Modeler" in text
    assert "__INITIAL_STATE__" not in text
    assert "display: none" not in text


def test_fetch_jd_text_handles_json_ats_payload(monkeypatch):
    payload = {
        "title": "Senior Systems Engineer",
        "description": "<p>Build <b>SysML</b> architectures under <em>DO-178C</em>.</p>",
    }

    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "application/json"}
        text = json.dumps(payload)

        def raise_for_status(self):
            return None

        def json(self):
            return payload

    monkeypatch.setattr("scripts.jd_analyzer.requests.get", lambda *a, **kw: FakeResponse())

    text = fetch_jd_text("https://api.lever.co/v0/postings/acme/123")
    assert "Senior Systems Engineer" in text
    assert "Build SysML architectures under DO-178C." in text


def test_load_opening_by_id_finds_known_opening():
    op = load_opening_by_id("AIRBUS-JR10437140")
    assert op["company"] == "Airbus India"


def test_load_opening_by_id_raises_key_error_when_missing():
    with pytest.raises(KeyError):
        load_opening_by_id("NONEXISTENT-OPENING-999")


def test_analyze_jd_identifies_matched_skills_and_gaps():
    profile = load_master_profile()
    opening = {
        "id": "TEST-1",
        "company": "Airbus India",
        "title": "Lead Systems Engineer - MBSE",
        "location": "Bangalore",
        "seniority": "Lead",
        "skills_matched": ["MBSE", "SysML"],
    }
    jd_text = (
        "Seeking Lead Systems Engineer in Bangalore with Cameo Systems Modeler, "
        "SysML, ARP4754A, DO-178C, and Teamcenter Polarion experience."
    )
    result = analyze_jd(opening, jd_text, profile)
    assert "Cameo" in result["matched_skills"] or "SysML" in result["matched_skills"]
    assert "ARP4754A" in result["matched_standards"]
    assert "DO-178C" in result["matched_standards"]
    assert isinstance(result["skill_gaps"], list)
    assert any("polarion" in g.lower() or "teamcenter" in g.lower() for g in result["skill_gaps"])


def test_analyze_jd_detects_missing_standards_and_avoids_false_gap_for_verified_simulink():
    profile = load_master_profile()
    opening = {
        "id": "TEST-2",
        "company": "Collins Aerospace",
        "title": "Principal Systems Engineer",
        "location": "Bengaluru",
        "seniority": "Principal",
    }
    jd_text = (
        "Principal Systems Engineer in Bengaluru working with Simulink, Capella, "
        "DO-160, AFDX, ARINC 429, MIL-STD-882E, and SysML v2."
    )
    result = analyze_jd(opening, jd_text, profile)
    assert "Simulink" in result["matched_skills"]
    assert "Simulink" not in result["skill_gaps"]
    assert "Capella" in result["skill_gaps"]
    assert "DO-160" in result["missing_standards"]
    assert "AFDX" in result["missing_standards"]
    assert "ARINC 429" in result["missing_standards"]
    assert "MIL-STD-882E" in result["missing_standards"]
    assert "SysML v2" in result["missing_standards"]
    assert result["seniority_alignment"].startswith("Strong")
    assert "Bangalore" in result["location_alignment"] or "Bengaluru" in result["location_alignment"]
    assert len(result["recommended_angles"]) >= 2


def test_save_analysis_writes_json_and_markdown(tmp_path):
    analysis = {
        "opening_id": "TEST-1",
        "company": "Airbus India",
        "title": "Lead Systems Engineer",
        "matched_skills": ["MBSE", "SysML"],
        "skill_gaps": ["Polarion"],
        "matched_standards": ["ARP4754A"],
        "missing_standards": [],
        "seniority_alignment": "Strong",
        "location_alignment": "Bangalore match",
        "priority_keywords": ["MBSE", "SysML", "ARP4754A"],
        "recommended_angles": ["Highlight 777-8F DTx MBSE leadership"],
        "analyzed_at": "2026-11-27",
    }
    json_path, md_path = save_analysis(analysis, applications_dir=tmp_path)
    assert json_path == tmp_path / "TEST-1" / "analysis.json"
    assert md_path == tmp_path / "TEST-1" / "analysis.md"
    assert json_path.exists() and md_path.exists()
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded["opening_id"] == "TEST-1"
    md_text = md_path.read_text(encoding="utf-8")
    assert "Airbus India" in md_text
    assert "Polarion" in md_text
    assert "ARP4754A" in md_text


def test_cli_main_analyzes_from_jd_file(tmp_path):
    jd_file = tmp_path / "jd.txt"
    jd_file.write_text(
        "Lead Systems Engineer in Bangalore using MBSE, Cameo Systems Modeler, DOORS, ARP4754A, and Jama.",
        encoding="utf-8",
    )
    apps_dir = tmp_path / "applications"
    exit_code = main([
        "--id",
        "AIRBUS-JR10437140",
        "--jd-file",
        str(jd_file),
        "--applications-dir",
        str(apps_dir),
    ])
    assert exit_code == 0
    assert (apps_dir / "AIRBUS-JR10437140" / "analysis.json").exists()
    assert (apps_dir / "AIRBUS-JR10437140" / "analysis.md").exists()
