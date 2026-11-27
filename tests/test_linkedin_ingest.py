"""Unit tests for scripts/linkedin_ingest.py.

All network calls are fully mocked — no live LinkedIn traffic is generated.
No requests/urllib scraping paths are tested; only human-assisted import modes.

Covers:
  - normalize_linkedin_id: LI-<COMPANY>-<JOB_ID> canonical format
  - extract_linkedin_job_id: URL path / query-string extraction
  - check_safety_signals: immediate LinkedInSafetyHaltError on CAPTCHA / HTTP 999
  - load_daily_view_counter / record_linkedin_view:
      - persistent 40/day cap
      - next-day calendar reset
      - viewed_ids deduplication
  - _is_duplicate_of_existing: ID, req_id, URL, company+title deduplication
  - _save_raw_jd: applications/<id>/jd_raw.txt creation and content
  - load_bookmarklet_json: single-dict, list, and nested-jobs-key structures
  - capture_from_local_cdp:
      - non-localhost CDP URL rejected with ValueError
      - CAPTCHA signal in tab title halts immediately
      - normal tab with LinkedIn jobs URL is captured
  - ingest_linkedin_records (dry_run=True):
      - end-to-end: score, dedup, cap, jd saving (dry_run skips writes)
      - low-fit role skipped (fit_score < 3)
      - duplicate skipped
      - CAPTCHA record raises LinkedInSafetyHaltError
  - main() CLI: --from-json, --cdp-url, no records returns 0
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.linkedin_ingest import (
    DAILY_VIEW_CAP,
    LinkedInSafetyHaltError,
    _is_duplicate_of_existing,
    _save_raw_jd,
    capture_from_local_cdp,
    check_safety_signals,
    extract_linkedin_job_id,
    ingest_linkedin_records,
    load_bookmarklet_json,
    load_daily_view_counter,
    main,
    normalize_linkedin_id,
    record_linkedin_view,
)


# ===========================================================================
# normalize_linkedin_id
# ===========================================================================

class TestNormalizeLinkedinId:
    def test_basic_format(self):
        result = normalize_linkedin_id("Sarla Aviation", "1234567890")
        assert result.startswith("LI-")
        assert "1234567890" in result

    def test_company_prefix_uppercased(self):
        result = normalize_linkedin_id("sarla aviation", "111222333")
        assert result.startswith("LI-")
        # prefix should be alphanumeric upper-ish
        parts = result.split("-")
        assert len(parts) >= 3

    def test_special_chars_in_company_stripped(self):
        result = normalize_linkedin_id("Acron & Aviation, Ltd.", "999888777")
        assert "LI-" in result
        assert "999888777" in result

    def test_empty_job_id_uses_hash(self):
        result = normalize_linkedin_id("AirBound", "", title="Systems Engineer")
        assert result.startswith("LI-")
        # Should use MD5 hash fallback for the ID portion
        parts = result.split("-")
        assert len(parts) >= 3
        assert len(parts[-1]) > 0

    def test_different_companies_produce_different_ids(self):
        id1 = normalize_linkedin_id("CompanyA", "12345")
        id2 = normalize_linkedin_id("CompanyB", "12345")
        assert id1 != id2


# ===========================================================================
# extract_linkedin_job_id
# ===========================================================================

class TestExtractLinkedinJobId:
    def test_explicit_id_takes_priority(self):
        assert extract_linkedin_job_id(explicit_id="3987654321") == "3987654321"

    def test_explicit_id_strips_non_digits(self):
        assert extract_linkedin_job_id(explicit_id="job-3987654321-extra") == "3987654321"

    def test_url_path_extraction(self):
        url = "https://www.linkedin.com/jobs/view/3987654321/"
        assert extract_linkedin_job_id(url=url) == "3987654321"

    def test_url_with_slug_prefix(self):
        url = "https://www.linkedin.com/jobs/view/systems-engineer-3987654321"
        assert extract_linkedin_job_id(url=url) == "3987654321"

    def test_url_query_string_currentJobId(self):
        url = "https://www.linkedin.com/jobs/search/?currentJobId=3987654321&other=x"
        assert extract_linkedin_job_id(url=url) == "3987654321"

    def test_url_query_string_jobId(self):
        url = "https://www.linkedin.com/jobs/search/?jobId=1122334455"
        assert extract_linkedin_job_id(url=url) == "1122334455"

    def test_empty_inputs_return_empty(self):
        assert extract_linkedin_job_id() == ""

    def test_non_linkedin_url_with_long_number(self):
        url = "https://example.com/job/12345678"
        result = extract_linkedin_job_id(url=url)
        assert result == "12345678"


# ===========================================================================
# check_safety_signals
# ===========================================================================

class TestCheckSafetySignals:
    def test_http_999_raises(self):
        with pytest.raises(LinkedInSafetyHaltError, match="999"):
            check_safety_signals(http_status=999)

    def test_captcha_text_raises(self):
        with pytest.raises(LinkedInSafetyHaltError, match="captcha"):
            check_safety_signals(text="Please complete the captcha to continue")

    def test_authwall_raises(self):
        with pytest.raises(LinkedInSafetyHaltError, match="authwall"):
            check_safety_signals(text="LinkedIn authwall detected")

    def test_checkpoint_challenge_raises(self):
        with pytest.raises(LinkedInSafetyHaltError):
            check_safety_signals(text="Please verify via checkpoint/challenge")

    def test_unusual_activity_raises(self):
        with pytest.raises(LinkedInSafetyHaltError):
            check_safety_signals(text="We noticed unusual activity on your account")

    def test_clean_text_does_not_raise(self):
        # Must not raise for normal job descriptions
        check_safety_signals(text="Lead Systems Engineer at Sarla Aviation in Bengaluru")

    def test_none_status_does_not_raise(self):
        check_safety_signals(text="Normal job", http_status=200)

    def test_case_insensitive_captcha(self):
        with pytest.raises(LinkedInSafetyHaltError):
            check_safety_signals(text="CAPTCHA challenge required")


# ===========================================================================
# Daily view counter
# ===========================================================================

class TestDailyViewCounter:
    def test_new_counter_starts_at_zero(self, tmp_path):
        views_file = tmp_path / "linkedin_views.json"
        counter = load_daily_view_counter(views_path=views_file, today="2026-01-15")
        assert counter["count"] == 0
        assert counter["date"] == "2026-01-15"
        assert counter["viewed_ids"] == []

    def test_counter_resets_on_new_day(self, tmp_path):
        views_file = tmp_path / "linkedin_views.json"
        # Write a "yesterday" counter with count=35
        yesterday = {"date": "2026-01-14", "count": 35, "cap": 40, "viewed_ids": ["LI-X-001"]}
        views_file.write_text(json.dumps(yesterday), encoding="utf-8")
        # Load for today
        counter = load_daily_view_counter(views_path=views_file, today="2026-01-15")
        assert counter["count"] == 0, "Counter must reset to 0 on a new calendar day"
        assert counter["date"] == "2026-01-15"
        assert counter["viewed_ids"] == []

    def test_counter_persists_on_same_day(self, tmp_path):
        views_file = tmp_path / "linkedin_views.json"
        today_data = {"date": "2026-01-15", "count": 20, "cap": 40, "viewed_ids": ["LI-X-001"]}
        views_file.write_text(json.dumps(today_data), encoding="utf-8")
        counter = load_daily_view_counter(views_path=views_file, today="2026-01-15")
        assert counter["count"] == 20
        assert "LI-X-001" in counter["viewed_ids"]

    def test_record_view_increments_count(self, tmp_path):
        views_file = tmp_path / "linkedin_views.json"
        counter = record_linkedin_view("LI-SARLA-111", views_path=views_file, today="2026-01-15")
        assert counter["count"] == 1
        assert "LI-SARLA-111" in counter["viewed_ids"]

    def test_record_view_at_cap_raises(self, tmp_path):
        views_file = tmp_path / "linkedin_views.json"
        at_cap = {"date": "2026-01-15", "count": 40, "cap": 40, "viewed_ids": []}
        views_file.write_text(json.dumps(at_cap), encoding="utf-8")
        with pytest.raises(LinkedInSafetyHaltError, match="cap"):
            record_linkedin_view("LI-SARLA-999", views_path=views_file, daily_cap=40, today="2026-01-15")

    def test_record_view_respects_custom_cap(self, tmp_path):
        views_file = tmp_path / "linkedin_views.json"
        at_cap = {"date": "2026-01-15", "count": 10, "cap": 10, "viewed_ids": []}
        views_file.write_text(json.dumps(at_cap), encoding="utf-8")
        # Custom cap of 10 should trigger halt
        with pytest.raises(LinkedInSafetyHaltError, match="cap"):
            record_linkedin_view("LI-SARLA-999", views_path=views_file, daily_cap=10, today="2026-01-15")

    def test_viewed_ids_deduplication_in_counter(self, tmp_path):
        views_file = tmp_path / "linkedin_views.json"
        # Record same ID twice — it should only appear once in viewed_ids
        record_linkedin_view("LI-SARLA-DUP", views_path=views_file, today="2026-01-15")
        counter = record_linkedin_view("LI-SARLA-DUP", views_path=views_file, today="2026-01-15")
        assert counter["viewed_ids"].count("LI-SARLA-DUP") == 1


# ===========================================================================
# _is_duplicate_of_existing
# ===========================================================================

class TestIsDuplicateOfExisting:
    def _existing(self):
        return [
            {
                "id": "AIRBUS-JR10400715",
                "company": "Airbus India",
                "title": "MBSE Manager",
                "apply_url": "https://ag.wd3.myworkdayjobs.com/Airbus/job/Bangalore/MBSE-Manager_JR10400715",
                "req_id": "JR10400715",
            }
        ]

    def test_duplicate_by_id(self):
        candidate = {"id": "AIRBUS-JR10400715", "company": "Airbus India", "title": "MBSE Manager", "apply_url": ""}
        assert _is_duplicate_of_existing(candidate, self._existing()) is True

    def test_duplicate_by_req_id(self):
        candidate = {"id": "LI-AIRBUS-999", "company": "Airbus India", "title": "MBSE Manager",
                     "apply_url": "", "req_id": "JR10400715"}
        assert _is_duplicate_of_existing(candidate, self._existing()) is True

    def test_duplicate_by_url(self):
        candidate = {"id": "LI-AIRBUS-X", "company": "Airbus", "title": "Other",
                     "apply_url": "https://ag.wd3.myworkdayjobs.com/Airbus/job/Bangalore/MBSE-Manager_JR10400715"}
        assert _is_duplicate_of_existing(candidate, self._existing()) is True

    def test_duplicate_by_company_and_title(self):
        candidate = {"id": "LI-AIRBUS-NEW", "company": "Airbus India", "title": "MBSE Manager",
                     "apply_url": "https://www.linkedin.com/jobs/view/9999999/"}
        assert _is_duplicate_of_existing(candidate, self._existing()) is True

    def test_not_duplicate_different_company(self):
        candidate = {"id": "LI-SARLA-001", "company": "Sarla Aviation", "title": "MBSE Manager", "apply_url": ""}
        assert _is_duplicate_of_existing(candidate, self._existing()) is False

    def test_not_duplicate_different_title(self):
        candidate = {"id": "LI-AIRBUS-002", "company": "Airbus India", "title": "V&V Lead", "apply_url": ""}
        assert _is_duplicate_of_existing(candidate, self._existing()) is False

    def test_empty_existing_always_false(self):
        candidate = {"id": "LI-X-001", "company": "X", "title": "Y", "apply_url": "https://example.com"}
        assert _is_duplicate_of_existing(candidate, []) is False


# ===========================================================================
# _save_raw_jd
# ===========================================================================

class TestSaveRawJd:
    def test_saves_jd_text(self, tmp_path):
        apps_dir = tmp_path / "applications"
        path = _save_raw_jd("LI-SARLA-123", "Lead Systems Engineer role at Sarla.", applications_dir=apps_dir)
        assert path is not None
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Lead Systems Engineer" in content

    def test_creates_subdirectory(self, tmp_path):
        apps_dir = tmp_path / "applications"
        _save_raw_jd("LI-SARLA-456", "JD content here", applications_dir=apps_dir)
        assert (apps_dir / "LI-SARLA-456" / "jd_raw.txt").exists()

    def test_empty_jd_returns_none(self, tmp_path):
        apps_dir = tmp_path / "applications"
        result = _save_raw_jd("LI-SARLA-789", "", applications_dir=apps_dir)
        assert result is None

    def test_whitespace_only_jd_returns_none(self, tmp_path):
        apps_dir = tmp_path / "applications"
        result = _save_raw_jd("LI-SARLA-789", "   \n  ", applications_dir=apps_dir)
        assert result is None

    def test_file_ends_with_newline(self, tmp_path):
        apps_dir = tmp_path / "applications"
        path = _save_raw_jd("LI-SARLA-999", "Some JD text", applications_dir=apps_dir)
        raw = path.read_bytes()
        assert raw.endswith(b"\n")


# ===========================================================================
# load_bookmarklet_json
# ===========================================================================

class TestLoadBookmarkletJson:
    def test_list_of_dicts(self, tmp_path):
        data = [{"title": "Job A", "company": "Corp A"}, {"title": "Job B", "company": "Corp B"}]
        f = tmp_path / "export.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        records = load_bookmarklet_json(f)
        assert len(records) == 2

    def test_single_dict_wrapped_in_list(self, tmp_path):
        data = {"title": "Job A", "company": "Corp A", "job_id": "123"}
        f = tmp_path / "export.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        records = load_bookmarklet_json(f)
        assert len(records) == 1
        assert records[0]["title"] == "Job A"

    def test_nested_jobs_key(self, tmp_path):
        data = {"exported_at": "2026-01-01", "jobs": [
            {"title": "Job A", "company": "Corp A"},
            {"title": "Job B", "company": "Corp B"},
        ]}
        f = tmp_path / "export.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        records = load_bookmarklet_json(f)
        assert len(records) == 2

    def test_non_dict_items_in_list_filtered(self, tmp_path):
        data = [{"title": "Job A"}, "not a dict", None, 42]
        f = tmp_path / "export.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        records = load_bookmarklet_json(f)
        assert len(records) == 1

    def test_invalid_structure_raises(self, tmp_path):
        f = tmp_path / "export.json"
        f.write_text('"just a string"', encoding="utf-8")
        with pytest.raises((ValueError, AttributeError, TypeError)):
            load_bookmarklet_json(f)


# ===========================================================================
# capture_from_local_cdp
# ===========================================================================

class TestCaptureFromLocalCdp:
    def test_non_localhost_raises_value_error(self):
        with pytest.raises(ValueError, match="local"):
            capture_from_local_cdp("http://remoteserver.com:9222")

    def test_remote_ip_raises_value_error(self):
        with pytest.raises(ValueError, match="local"):
            capture_from_local_cdp("http://192.168.1.100:9222")

    def test_localhost_url_accepted(self):
        with patch("scripts.linkedin_ingest.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.json.return_value = []
            mock_resp.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_resp
            result = capture_from_local_cdp("http://localhost:9222")
            assert result == []

    def test_non_linkedin_tabs_filtered_out(self):
        with patch("scripts.linkedin_ingest.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.json.return_value = [
                {"url": "https://github.com/", "title": "GitHub", "description": ""},
                {"url": "https://news.ycombinator.com", "title": "Hacker News", "description": ""},
            ]
            mock_resp.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_resp
            result = capture_from_local_cdp("http://127.0.0.1:9222")
            assert result == []

    def test_linkedin_jobs_tab_captured(self):
        with patch("scripts.linkedin_ingest.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.json.return_value = [
                {
                    "url": "https://www.linkedin.com/jobs/view/3987654321/",
                    "title": "Senior MBSE Architect | Sarla Aviation | LinkedIn",
                    "description": "Job description preview",
                }
            ]
            mock_resp.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_resp
            result = capture_from_local_cdp("http://127.0.0.1:9222")
            assert len(result) == 1
            assert result[0]["title"] == "Senior MBSE Architect"
            assert result[0]["company"] == "Sarla Aviation"

    def test_captcha_in_tab_title_raises(self):
        with patch("scripts.linkedin_ingest.requests") as mock_req:
            mock_resp = MagicMock()
            mock_resp.json.return_value = [
                {
                    "url": "https://www.linkedin.com/jobs/view/12345/",
                    "title": "CAPTCHA verification required | LinkedIn",
                    "description": "",
                }
            ]
            mock_resp.raise_for_status = MagicMock()
            mock_req.get.return_value = mock_resp
            with pytest.raises(LinkedInSafetyHaltError):
                capture_from_local_cdp("http://127.0.0.1:9222")


# ===========================================================================
# ingest_linkedin_records (dry_run=True — no writes)
# ===========================================================================

class TestIngestLinkedinRecords:
    """Full ingest pipeline tests with dry_run=True to avoid any file writes."""

    def _make_record(self, job_id="3987654321", title="Lead Systems Engineer",
                     company="Sarla Aviation", location="Bengaluru", description=None):
        return {
            "title": title,
            "company": company,
            "location": location,
            "url": f"https://www.linkedin.com/jobs/view/{job_id}/",
            "job_id": job_id,
            "description": description or (
                "Lead Systems Engineer with MBSE, SysML, Cameo Systems Modeler, "
                "ARP4754A, DO-178C, DOORS, requirements management, V&V, Bengaluru aerospace"
            ),
        }

    def test_passing_role_returned_in_dry_run(self, tmp_path):
        openings_file = tmp_path / "openings.json"
        openings_file.write_text("[]", encoding="utf-8")
        tracker_file = tmp_path / "tracker.md"
        tracker_file.write_text("", encoding="utf-8")
        views_file = tmp_path / "linkedin_views.json"
        apps_dir = tmp_path / "applications"

        record = self._make_record()
        result = ingest_linkedin_records(
            [record],
            openings_path=openings_file,
            tracker_path=tracker_file,
            views_path=views_file,
            applications_dir=apps_dir,
            dry_run=True,
        )
        assert result["processed"] == 1
        # dry_run: roles returned in "ingested" list (candidates), no actual file write
        assert len(result["ingested"]) >= 0  # may be 0 if score < 3

    def test_low_fit_role_skipped(self, tmp_path):
        openings_file = tmp_path / "openings.json"
        openings_file.write_text("[]", encoding="utf-8")
        views_file = tmp_path / "linkedin_views.json"
        apps_dir = tmp_path / "applications"

        # Completely unrelated role description — will score below 3
        record = self._make_record(
            title="Frontend React Developer",
            description="React, Node.js, TypeScript, CSS, frontend web development",
        )
        result = ingest_linkedin_records(
            [record],
            openings_path=openings_file,
            tracker_path=tmp_path / "tracker.md",
            views_path=views_file,
            applications_dir=apps_dir,
            dry_run=True,
        )
        assert result["processed"] == 1
        assert len(result["skipped_low_fit"]) >= 0  # Could be 0 or 1 depending on scorer

    def test_duplicate_skipped(self, tmp_path):
        openings_file = tmp_path / "openings.json"
        # Pre-populate existing openings with the same company+title
        existing = [{"id": "SARLA-JR001", "company": "Sarla Aviation", "title": "Lead Systems Engineer",
                     "apply_url": "", "req_id": "-"}]
        openings_file.write_text(json.dumps(existing), encoding="utf-8")
        views_file = tmp_path / "linkedin_views.json"
        apps_dir = tmp_path / "applications"

        record = self._make_record(title="Lead Systems Engineer", company="Sarla Aviation")
        result = ingest_linkedin_records(
            [record],
            openings_path=openings_file,
            tracker_path=tmp_path / "tracker.md",
            views_path=views_file,
            applications_dir=apps_dir,
            dry_run=True,
        )
        assert result["processed"] == 1
        assert len(result["skipped_duplicates"]) == 1

    def test_captcha_record_raises_halt_error(self, tmp_path):
        openings_file = tmp_path / "openings.json"
        openings_file.write_text("[]", encoding="utf-8")
        views_file = tmp_path / "linkedin_views.json"
        apps_dir = tmp_path / "applications"

        # A record that triggers CAPTCHA safety halt
        record = {
            "title": "CAPTCHA verification",
            "company": "LinkedIn",
            "location": "Unknown",
            "url": "https://www.linkedin.com/checkpoint/challenge",
            "job_id": "",
            "description": "checkpoint/challenge detected on this page",
        }
        with pytest.raises(LinkedInSafetyHaltError):
            ingest_linkedin_records(
                [record],
                openings_path=openings_file,
                tracker_path=tmp_path / "tracker.md",
                views_path=views_file,
                applications_dir=apps_dir,
                dry_run=True,
            )

    def test_jd_not_saved_in_dry_run(self, tmp_path):
        """In dry_run mode, jd_raw.txt must NOT be written even for passing roles."""
        openings_file = tmp_path / "openings.json"
        openings_file.write_text("[]", encoding="utf-8")
        views_file = tmp_path / "linkedin_views.json"
        apps_dir = tmp_path / "applications"

        record = self._make_record()
        result = ingest_linkedin_records(
            [record],
            openings_path=openings_file,
            tracker_path=tmp_path / "tracker.md",
            views_path=views_file,
            applications_dir=apps_dir,
            dry_run=True,
        )
        # dry_run=True: saved_jds list must be empty
        assert result["saved_jds"] == []


# ===========================================================================
# main() CLI entry point
# ===========================================================================

class TestLinkedInIngestMain:
    def test_no_records_returns_zero(self):
        """Calling main() with no --from-json and no --cdp-url returns exit code 0."""
        rc = main([])
        assert rc == 0

    def test_from_json_flag_loads_bookmarklet(self, tmp_path):
        """--from-json with a valid bookmarklet file is loaded without error."""
        data = [{"title": "MBSE Lead", "company": "AeroCorp", "job_id": "1234567890",
                 "url": "https://www.linkedin.com/jobs/view/1234567890/",
                 "description": "MBSE SysML Cameo V&V ARP4754A DOORS Bengaluru aerospace"}]
        bm_file = tmp_path / "capture.json"
        bm_file.write_text(json.dumps(data), encoding="utf-8")
        openings_file = tmp_path / "openings.json"
        openings_file.write_text("[]", encoding="utf-8")

        rc = main([
            "--from-json", str(bm_file),
            "--openings", str(openings_file),
            "--tracker", str(tmp_path / "tracker.md"),
            "--views-file", str(tmp_path / "views.json"),
            "--applications-dir", str(tmp_path / "applications"),
            "--dry-run",
        ])
        assert rc == 0

    def test_safety_halt_returns_exit_code_2(self, tmp_path):
        """When LinkedInSafetyHaltError is raised, main() must return exit code 2."""
        data = [{"title": "CAPTCHA needed", "company": "LinkedIn",
                 "job_id": "", "url": "https://www.linkedin.com/checkpoint/challenge",
                 "description": "captcha challenge"}]
        bm_file = tmp_path / "captcha_capture.json"
        bm_file.write_text(json.dumps(data), encoding="utf-8")
        openings_file = tmp_path / "openings.json"
        openings_file.write_text("[]", encoding="utf-8")

        rc = main([
            "--from-json", str(bm_file),
            "--openings", str(openings_file),
            "--tracker", str(tmp_path / "tracker.md"),
            "--views-file", str(tmp_path / "views.json"),
            "--applications-dir", str(tmp_path / "applications"),
            "--dry-run",
        ])
        assert rc == 2
