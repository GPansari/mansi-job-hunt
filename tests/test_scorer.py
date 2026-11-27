import json
import subprocess
import sys
from scripts.scorer import score_job

candidate = {
    "target_titles": ["Lead Systems Engineer", "MBSE Lead", "Avionics Lead"],
    "core_skills": ["MBSE", "SysML", "Cameo", "DOORS", "ARP4754A"],
    "target_locations": ["Bangalore", "Bengaluru"],
    "excluded_keywords": ["Intern", "Fresher", "Apprentice", "Frontend", "Fullstack"]
}


def test_high_fit_role():
    job = {
        "title": "MBSE Capability Verification & Validation Leader",
        "description": "Leading MBSE adoption using Cameo, SysML, and DOORS in Bangalore.",
        "location": "Bangalore"
    }
    result = score_job(job, candidate)
    assert result["fit_score"] >= 4
    assert isinstance(result["fit_score"], int)
    assert "MBSE" in result["skills_matched"]
    assert "Cameo" in result["skills_matched"]
    assert result["passed_gate"] is True
    assert isinstance(result["fit_rationale"], str) and len(result["fit_rationale"]) > 0


def test_excluded_role_fails_gate():
    job = {
        "title": "Software Engineering Intern - Web Fullstack",
        "description": "React and Node.js intern in Bangalore.",
        "location": "Bangalore"
    }
    result = score_job(job, candidate)
    assert result["fit_score"] == 1
    assert isinstance(result["fit_score"], int)
    assert result["passed_gate"] is False
    assert "excluded" in result["fit_rationale"].lower()


def test_different_location_penalized():
    job = {
        "title": "Lead Systems Engineer",
        "description": "MBSE and SysML modeling.",
        "location": "Hyderabad"
    }
    result = score_job(job, candidate)
    assert result["fit_score"] <= 3
    assert isinstance(result["fit_score"], int)


def test_word_boundary_does_not_false_trigger_excluded_keyword():
    # 'Intern' should not trigger on 'Internal'
    job = {
        "title": "Lead Systems Engineer - Internal Programs",
        "description": "Leading internal aerospace MBSE and Cameo modeling in Bangalore.",
        "location": "Bangalore"
    }
    result = score_job(job, candidate)
    assert result["fit_score"] >= 4
    assert result["passed_gate"] is True


def test_excluded_keyword_in_description_disqualifies():
    job = {
        "title": "Lead Systems Engineer",
        "description": "We are seeking a Fresher or Apprentice to support MBSE tasks.",
        "location": "Bangalore"
    }
    result = score_job(job, candidate)
    assert result["fit_score"] == 1
    assert result["passed_gate"] is False


def test_skills_cap_at_two_point_five():
    # 5 or more skills should max out at +2.5
    job = {
        "title": "Lead Systems Engineer",
        "description": "Expertise in MBSE, SysML, Cameo, DOORS, and ARP4754A required.",
        "location": "Bangalore"
    }
    result = score_job(job, candidate)
    assert result["fit_score"] == 5
    assert len(result["skills_matched"]) == 5
    assert result["passed_gate"] is True


def test_minimum_score_clamping():
    # Unmatched title, zero skills, outside location -> baseline 1.0 - 1.0 = 0.0 -> clamped to 1
    job = {
        "title": "HR Specialist",
        "description": "General human resources management.",
        "location": "Pune"
    }
    result = score_job(job, candidate)
    assert result["fit_score"] == 1
    assert result["passed_gate"] is False
    assert len(result["skills_matched"]) == 0


def test_missing_or_empty_job_fields_handled_safely():
    job = {}
    result = score_job(job, candidate)
    assert result["fit_score"] == 1
    assert result["passed_gate"] is False
    assert result["skills_matched"] == []


def test_default_candidate_profile_from_file():
    # When candidate is None, load canonical profile/candidate.json
    job = {
        "title": "Avionics Lead Engineer",
        "description": "SysML and MBSE architecture for commercial aircraft.",
        "location": "Bengaluru"
    }
    result = score_job(job)
    assert result["fit_score"] >= 4
    assert result["passed_gate"] is True
    assert "MBSE" in result["skills_matched"]


def test_cli_execution():
    res = subprocess.run([
        sys.executable, "scripts/scorer.py", "--help"
    ], capture_output=True, text=True)
    assert res.returncode == 0
    assert "score" in res.stdout.lower()
    assert "--score-all" in res.stdout
    assert "--update" in res.stdout
    assert "--save" in res.stdout


def test_cli_score_all_update(tmp_path):
    openings_file = tmp_path / "openings.json"
    tracker_file = tmp_path / "Openings_Tracker.md"

    initial_openings = [
        {
            "id": "TEST-1",
            "company": "Airbus India",
            "title": "Lead Systems Engineer",
            "description": "Cameo and SysML modeling in Bangalore.",
            "location": "Bangalore",
            "req_id": "JR123",
            "seniority": "Lead",
            "fit_score": 1,
            "status": "Not Applied",
            "apply_url": "https://example.com/apply1",
            "next_action": "Review",
            "skills_matched": [],
            "fit_rationale": "Initial uncalculated rationale",
        },
        {
            "id": "TEST-2",
            "company": "Collins Aerospace",
            "title": "Frontend React Intern",
            "description": "Internship in Bangalore.",
            "location": "Bangalore",
            "req_id": "JR456",
            "seniority": "Intern",
            "fit_score": 5,
            "status": "Not Applied",
            "apply_url": "https://example.com/apply2",
            "next_action": "Review",
            "skills_matched": ["MBSE"],
            "fit_rationale": "Incorrect score",
        },
    ]
    openings_file.write_text(json.dumps(initial_openings, indent=2), encoding="utf-8")

    res = subprocess.run([
        sys.executable,
        "scripts/scorer.py",
        "--score-all",
        "--update",
        "--openings",
        str(openings_file),
        "--tracker",
        str(tracker_file),
    ], capture_output=True, text=True)

    assert res.returncode == 0
    assert "Updated 2 openings" in res.stdout
    assert "Synchronized Markdown tracker" in res.stdout

    # Verify openings.json was updated with freshly calculated scores
    updated_openings = json.loads(openings_file.read_text(encoding="utf-8"))
    assert len(updated_openings) == 2

    # TEST-1 (Lead Systems Engineer, Cameo/SysML, Bangalore) -> fit_score >= 4
    assert updated_openings[0]["fit_score"] >= 4
    assert "Cameo" in updated_openings[0]["skills_matched"]
    assert "SysML" in updated_openings[0]["skills_matched"]
    assert "Final fit score" in updated_openings[0]["fit_rationale"]

    # TEST-2 (Intern) -> disqualified, fit_score == 1
    assert updated_openings[1]["fit_score"] == 1
    assert "Disqualified" in updated_openings[1]["fit_rationale"]

    # Verify tracker Markdown was created/synchronized
    assert tracker_file.exists()
    tracker_content = tracker_file.read_text(encoding="utf-8")
    assert "Airbus India" in tracker_content
    assert "Collins Aerospace" in tracker_content


def test_scorer_matches_master_dossier_skills_and_target_domains():
    job = {
        "title": "Avionics Systems Architect",
        "description": "Requires SysML v2, ARINC 429, AFDX, MSOSA, DESE, ReqHub, DataHub, and AS9100 for eVTOL and UAV programs.",
        "location": "Bengaluru",
    }
    res = score_job(job)
    assert res["fit_score"] >= 4
    for skill in ("SysML v2", "ARINC 429", "AFDX", "MSOSA", "DESE", "ReqHub", "DataHub", "AS9100"):
        assert skill in res["skills_matched"]
    assert "eVTOL" in res["domains_matched"] or "UAV" in res["domains_matched"]


def test_non_engineering_zero_skill_gate():
    job = {
        "title": "Corporate Communications Manager",
        "description": "Lead internal communications, executive messaging, and brand strategy.",
        "location": "Bengaluru",
    }
    res = score_job(job)
    assert res["skills_matched"] == []
    assert res["fit_score"] <= 2
    assert res["passed_gate"] is False
    assert "capped <= 2" in res["fit_rationale"]

