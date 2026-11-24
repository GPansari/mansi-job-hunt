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
