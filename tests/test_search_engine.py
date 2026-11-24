"""Unit tests for Multi-Tier Search & Discovery Utilities."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

from scripts.search_engine import (
    LINKEDIN_SAFETY_ENVELOPE,
    _make_company_prefix,
    _parse_workday_url,
    generate_tier1_dorking_queries,
    infer_seniority,
    ingest_openings,
    query_public_ats_feed,
    scan_all_ats_feeds,
)


def test_generate_dorking_queries():
    candidate = {
        "core_skills": ["MBSE", "SysML"],
        "target_locations": ["Bangalore"],
    }
    queries = generate_tier1_dorking_queries(candidate)
    assert any("site:linkedin.com/jobs" in q for q in queries)
    assert any("Bangalore" in q for q in queries)


def test_generate_dorking_queries_defaults_and_aggregators():
    # Empty candidate profile should fall back gracefully
    queries = generate_tier1_dorking_queries({})
    assert len(queries) >= 3
    assert any("site:linkedin.com/jobs" in q for q in queries)
    assert any("myworkdayjobs.com" in q or "greenhouse.io" in q for q in queries)

    # Check distinct query generation
    assert len(queries) == len(set(queries))


def test_linkedin_safety_envelope_constants():
    assert LINKEDIN_SAFETY_ENVELOPE["scroll_chunk_min_px"] == 250
    assert LINKEDIN_SAFETY_ENVELOPE["scroll_chunk_max_px"] == 600
    assert LINKEDIN_SAFETY_ENVELOPE["pause_min_sec"] == 2
    assert LINKEDIN_SAFETY_ENVELOPE["pause_max_sec"] == 6
    assert LINKEDIN_SAFETY_ENVELOPE["max_views_per_day"] == 50
    assert LINKEDIN_SAFETY_ENVELOPE["duty_cycle_work_min"] == 15
    assert LINKEDIN_SAFETY_ENVELOPE["duty_cycle_rest_min"] == 20


def test_infer_seniority_and_company_prefix():
    assert infer_seniority("Lead Systems Engineer") == "Lead"
    assert infer_seniority("Principal Systems Architect") == "Lead"
    assert infer_seniority("Senior MBSE Engineer") == "Senior"
    assert infer_seniority("Systems Engineering Manager") == "Manager"
    assert infer_seniority("MBSE Capability Verification & Validation Leader") == "Lead"
    assert infer_seniority("Engineering Director") == "Director"
    assert infer_seniority("Systems Engineer") == "Mid/Senior"

    assert _make_company_prefix("Airbus India") == "AIRBUS"
    assert _make_company_prefix("Collins Aerospace (RTX)") == "COLLINS"
    assert _make_company_prefix("GE Aerospace") == "GEAEROSP"
    assert _make_company_prefix("") == "JOB"


def test_parse_workday_url():
    host, tenant, site = _parse_workday_url("https://ag.wd3.myworkdayjobs.com/Airbus", {})
    assert host == "ag.wd3.myworkdayjobs.com"
    assert site == "Airbus"

    host, tenant, site = _parse_workday_url(
        "https://globalhr.wd5.myworkdayjobs.com/en-US/RTX_Careers",
        {"workday_tenant": "globalhr"}
    )
    assert host == "globalhr.wd5.myworkdayjobs.com"
    assert tenant == "globalhr"
    assert site == "RTX_Careers"


def test_query_public_ats_feed_workday(requests_mock):
    company = {
        "name": "Airbus India",
        "ats_type": "workday",
        "careers_url": "https://ag.wd3.myworkdayjobs.com/Airbus",
    }
    mock_response = {
        "total": 1,
        "jobPostings": [
            {
                "title": "MBSE Capability Verification & Validation Leader",
                "externalPath": "/job/Bangalore/MBSE-Capability-Leader_JR10400715",
                "bulletFields": ["JR10400715", "Bangalore, India"],
                "locationsText": "Bangalore, India",
                "postedOn": "Posted 5 Days Ago",
            }
        ],
    }
    requests_mock.post(
        "https://ag.wd3.myworkdayjobs.com/wday/cxs/Airbus/Airbus/jobs",
        json=mock_response,
    )

    openings = query_public_ats_feed(company, timeout=5)
    assert len(openings) == 1
    job = openings[0]
    assert job["company"] == "Airbus India"
    assert "MBSE" in job["title"]
    assert job["req_id"] == "JR10400715"
    assert "https://ag.wd3.myworkdayjobs.com" in job["apply_url"]
    assert job["fit_score"] >= 3
    assert job["passed_gate"] is True

    # Verify default searchText fallback to "Systems Engineer"
    assert requests_mock.last_request.json()["searchText"] == "Systems Engineer"

    # Verify custom search_text is preserved when provided
    company_custom = {
        "name": "Airbus India",
        "ats_type": "workday",
        "careers_url": "https://ag.wd3.myworkdayjobs.com/Airbus",
        "search_text": "MBSE Specialist",
    }
    query_public_ats_feed(company_custom, timeout=5)
    assert requests_mock.last_request.json()["searchText"] == "MBSE Specialist"


def test_query_public_ats_feed_greenhouse(requests_mock):
    company = {
        "name": "Sarla Aviation",
        "ats_type": "greenhouse",
        "careers_url": "https://boards.greenhouse.io/sarlaaviation",
    }
    mock_response = {
        "jobs": [
            {
                "id": 987654,
                "title": "Lead Systems Engineer (MBSE)",
                "location": {"name": "Bengaluru, India"},
                "absolute_url": "https://boards.greenhouse.io/sarlaaviation/jobs/987654",
                "updated_at": "2026-11-20T10:00:00Z",
                "departments": [{"name": "Flight Sciences"}],
            }
        ]
    }
    requests_mock.get(
        "https://boards-api.greenhouse.io/v1/boards/sarlaaviation/jobs?content=true",
        json=mock_response,
    )

    openings = query_public_ats_feed(company, timeout=5)
    assert len(openings) == 1
    job = openings[0]
    assert job["company"] == "Sarla Aviation"
    assert job["req_id"] == "987654"
    assert job["team"] == "Flight Sciences"
    assert job["fit_score"] >= 4
    assert job["passed_gate"] is True


def test_query_public_ats_feed_lever(requests_mock):
    company = {
        "name": "Bellatrix Aerospace",
        "ats_type": "lever",
        "careers_url": "https://jobs.lever.co/bellatrix",
    }
    mock_response = [
        {
            "id": "lever-1234",
            "text": "Avionics Lead Engineer",
            "categories": {
                "location": "Bangalore",
                "team": "Avionics & Systems",
                "commitment": "Full Time",
            },
            "hostedUrl": "https://jobs.lever.co/bellatrix/lever-1234",
            "descriptionPlain": "Leading avionics architecture and SysML modeling.",
        }
    ]
    requests_mock.get(
        "https://api.lever.co/v0/postings/bellatrix?mode=json",
        json=mock_response,
    )

    openings = query_public_ats_feed(company, timeout=5)
    assert len(openings) == 1
    job = openings[0]
    assert job["company"] == "Bellatrix Aerospace"
    assert job["title"] == "Avionics Lead Engineer"
    assert job["req_id"] == "lever-1234"
    assert job["fit_score"] >= 3


def test_query_public_ats_feed_ashby(requests_mock):
    company = {
        "name": "Pixxel Space",
        "ats_type": "ashby",
        "careers_url": "https://jobs.ashbyhq.com/pixxel",
    }
    mock_response = {
        "jobs": [
            {
                "id": "ashby-999",
                "title": "Systems Architecture Lead",
                "location": "Bangalore, India",
                "jobUrl": "https://jobs.ashbyhq.com/pixxel/ashby-999",
                "department": "Space Systems",
            }
        ]
    }
    requests_mock.post(
        "https://api.ashbyhq.com/posting-api/job-board/pixxel",
        json=mock_response,
    )

    openings = query_public_ats_feed(company, timeout=5)
    assert len(openings) == 1
    job = openings[0]
    assert job["company"] == "Pixxel Space"
    assert job["req_id"] == "ashby-999"
    assert job["fit_score"] >= 3


def test_query_public_ats_feed_resilience_to_errors(requests_mock):
    company = {
        "name": "Error Corp",
        "ats_type": "greenhouse",
        "careers_url": "https://boards.greenhouse.io/errorcorp",
    }
    # 500 Internal Server Error
    requests_mock.get(
        "https://boards-api.greenhouse.io/v1/boards/errorcorp/jobs?content=true",
        status_code=500,
    )
    openings = query_public_ats_feed(company, timeout=5)
    assert openings == []

    # Connection Timeout
    requests_mock.get(
        "https://boards-api.greenhouse.io/v1/boards/errorcorp/jobs?content=true",
        exc=requests.exceptions.ConnectTimeout,
    )
    openings = query_public_ats_feed(company, timeout=5)
    assert openings == []


def test_query_public_ats_feed_unsupported_or_custom_ats():
    company = {
        "name": "HAL",
        "ats_type": "custom",
        "careers_url": "https://hal-india.co.in",
    }
    openings = query_public_ats_feed(company, timeout=5)
    assert openings == []


def test_scan_all_ats_feeds_filtering(requests_mock):
    companies = [
        {
            "name": "Airbus India",
            "ats_type": "workday",
            "careers_url": "https://ag.wd3.myworkdayjobs.com/Airbus",
        },
        {
            "name": "Sarla Aviation",
            "ats_type": "greenhouse",
            "careers_url": "https://boards.greenhouse.io/sarlaaviation",
        },
        {
            "name": "HAL",
            "ats_type": "custom",
            "careers_url": "https://hal-india.co.in",
        },
    ]

    requests_mock.post(
        "https://ag.wd3.myworkdayjobs.com/wday/cxs/Airbus/Airbus/jobs",
        json={
            "total": 1,
            "jobPostings": [
                {
                    "title": "MBSE Leader",
                    "externalPath": "/job/1",
                    "bulletFields": ["JR101", "Bangalore"],
                }
            ],
        },
    )

    # Filter for Airbus only
    results = scan_all_ats_feeds(companies, company_filter="Airbus")
    assert len(results) == 1
    assert results[0]["company"] == "Airbus India"


def test_ingest_openings_deduplication_and_sync(tmp_path):
    json_path = tmp_path / "openings.json"
    md_path = tmp_path / "Openings_Tracker.md"

    initial_openings = [
        {
            "id": "EXISTING-1",
            "company": "Existing Co",
            "team": "Systems",
            "title": "Lead Systems Engineer",
            "location": "Bangalore",
            "req_id": "REQ-1",
            "seniority": "Lead",
            "fit_score": 5,
            "fit_rationale": "High fit",
            "skills_matched": ["MBSE"],
            "apply_url": "https://example.com/1",
            "source": "Official",
            "status": "Not Applied",
            "date_discovered": "2026-11-20",
            "last_updated": "2026-11-20",
            "next_action": "Apply",
        }
    ]
    json_path.write_text(json.dumps(initial_openings))

    new_discovered = [
        # Duplicate by ID
        {
            "id": "EXISTING-1",
            "company": "Existing Co",
            "title": "Lead Systems Engineer",
            "fit_score": 5,
            "passed_gate": True,
            "apply_url": "https://example.com/other-url",
        },
        # Duplicate by URL
        {
            "id": "DIFF-ID",
            "company": "Existing Co",
            "title": "Lead Systems Engineer",
            "fit_score": 5,
            "passed_gate": True,
            "apply_url": "https://example.com/1",
        },
        # Fails gate (score < 3)
        {
            "id": "NEW-LOW-FIT",
            "company": "Low Fit Co",
            "title": "Frontend Intern",
            "fit_score": 1,
            "passed_gate": False,
            "apply_url": "https://example.com/low",
        },
        # Passing new role
        {
            "id": "NEW-ROLE-2",
            "company": "Target Aerospace",
            "team": "Avionics",
            "title": "MBSE Lead Engineer",
            "location": "Bangalore",
            "req_id": "TA-200",
            "seniority": "Lead",
            "fit_score": 5,
            "fit_rationale": "Direct MBSE match",
            "skills_matched": ["MBSE", "SysML"],
            "apply_url": "https://example.com/2",
            "source": "Official (Workday)",
            "status": "Not Applied",
            "date_discovered": "2026-11-24",
            "last_updated": "2026-11-24",
            "next_action": "Draft tailored resume",
            "passed_gate": True,
        },
    ]

    added = ingest_openings(new_discovered, json_path=json_path, md_path=md_path)
    assert len(added) == 1
    assert added[0]["id"] == "NEW-ROLE-2"

    saved_json = json.loads(json_path.read_text())
    assert len(saved_json) == 2
    assert saved_json[1]["id"] == "NEW-ROLE-2"

    md_content = md_path.read_text()
    assert "NEW-ROLE-2" in md_content or "Target Aerospace" in md_content


def test_cli_queries_output():
    res = subprocess.run(
        [sys.executable, "scripts/search_engine.py", "--queries"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "Tier 1 Google Dorking Queries" in res.stdout
    assert "site:linkedin.com/jobs" in res.stdout
    assert "Bangalore" in res.stdout
    assert "Safety limits" in res.stdout


def test_cli_help():
    res = subprocess.run(
        [sys.executable, "scripts/search_engine.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "--queries" in res.stdout
    assert "--scan-ats" in res.stdout
    assert "--ingest-new" in res.stdout


def test_ingest_openings_aborts_on_corrupted_file(tmp_path):
    json_path = tmp_path / "corrupt_openings.json"
    md_path = tmp_path / "Openings_Tracker.md"
    corrupt_content = "{ invalid json content: true "
    json_path.write_text(corrupt_content)

    new_discovered = [
        {
            "id": "NEW-ROLE-1",
            "company": "Target Aerospace",
            "title": "MBSE Lead Engineer",
            "fit_score": 5,
            "passed_gate": True,
            "apply_url": "https://example.com/1",
        }
    ]

    with pytest.raises(RuntimeError) as exc_info:
        ingest_openings(new_discovered, json_path=json_path, md_path=md_path)

    assert "Corrupted or unreadable" in str(exc_info.value)
    # Crucial: verify corrupt file was NOT overwritten or destroyed
    assert json_path.read_text() == corrupt_content


def test_punctuation_only_req_id_uses_hash_prefix(requests_mock):
    company = {
        "name": "Airbus India",
        "ats_type": "workday",
        "careers_url": "https://ag.wd3.myworkdayjobs.com/Airbus",
    }
    mock_response = {
        "total": 1,
        "jobPostings": [
            {
                "title": "MBSE Specialist",
                "externalPath": "/job/test",
                "bulletFields": ["---", "Bangalore, India"],
            }
        ],
    }
    requests_mock.post(
        "https://ag.wd3.myworkdayjobs.com/wday/cxs/Airbus/Airbus/jobs",
        json=mock_response,
    )
    openings = query_public_ats_feed(company, timeout=5)
    assert len(openings) == 1
    # ID should not be empty suffix like AIRBUS-
    assert openings[0]["id"] != "AIRBUS-"
    assert openings[0]["id"] != "AIRBUS---"
    assert len(openings[0]["id"]) > len("AIRBUS-")


def test_generate_dorking_queries_custom_domains():
    candidate = {
        "core_skills": ["MBSE"],
        "target_locations": ["Bangalore"],
        "target_domains": ["Hypersonics", "Autonomous Flight"],
    }
    queries = generate_tier1_dorking_queries(candidate)
    assert any("hypersonics" in q.lower() for q in queries)
    assert any("autonomous flight" in q.lower() for q in queries)

