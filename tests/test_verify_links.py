"""Unit tests for scripts/verify_links.py and related search_engine.py URL-typing logic.

All HTTP calls are fully mocked — no live network traffic is generated.
Covers:
  - classify_url_type: 3-tier classification for all ATS host patterns
  - _check_ats_api_direct: Lever and Greenhouse authoritative API verification
  - check_url_health: HTTP 429 → rate_limited (never expired), soft-404 body checks,
    board_role_anchor title+CTA dual requirement, restricted (403/999)
  - verify_board_role_cta: title presence (direct + token), CTA patterns
  - ingest_openings via search_engine: rejection of generic_portal and unverified board_role_anchor
  - verify_all_openings: metadata persistence written back to openings.json
  - Kula and Freshteam adapter URL classification
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure repo root is importable
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.verify_links import (
    CTA_PATTERNS,
    SOFT_404_PATTERNS,
    _check_ats_api_direct,
    _strip_html_text,
    check_url_health,
    classify_url_type,
    verify_all_openings,
    verify_board_role_cta,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _mock_response(status_code: int, text: str = "", url: str = "https://example.com") -> MagicMock:
    """Build a minimal requests.Response mock."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.url = url
    return resp


# ===========================================================================
# classify_url_type
# ===========================================================================

class TestClassifyUrlType:
    def test_empty_url_is_generic_portal(self):
        assert classify_url_type("") == "generic_portal"

    def test_hash_only_url_is_generic_portal(self):
        assert classify_url_type("#jobs") == "generic_portal"

    def test_na_placeholder(self):
        assert classify_url_type("N/A") == "generic_portal"

    def test_bare_careers_path_is_generic_portal(self):
        assert classify_url_type("https://example.com/careers") == "generic_portal"
        assert classify_url_type("https://example.com/jobs") == "generic_portal"
        assert classify_url_type("https://example.com/join-us") == "generic_portal"

    def test_lever_board_root_is_generic_portal(self):
        assert classify_url_type("https://jobs.lever.co/acronaviation") == "generic_portal"

    def test_lever_specific_job_is_direct_requisition(self):
        url = "https://jobs.lever.co/acronaviation/abc123-uuid-goes-here"
        assert classify_url_type(url) == "direct_requisition"

    def test_ashby_board_root_is_generic_portal(self):
        assert classify_url_type("https://jobs.ashbyhq.com/airbound") == "generic_portal"

    def test_ashby_specific_job_is_direct_requisition(self):
        url = "https://jobs.ashbyhq.com/airbound/some-job-id-12345"
        assert classify_url_type(url) == "direct_requisition"

    def test_greenhouse_board_root_is_generic_portal(self):
        assert classify_url_type("https://boards.greenhouse.io/sarla") == "generic_portal"

    def test_greenhouse_specific_job_is_direct_requisition(self):
        url = "https://boards.greenhouse.io/sarla/jobs/7654321"
        assert classify_url_type(url) == "direct_requisition"

    def test_workday_root_is_generic_portal(self):
        assert classify_url_type("https://boeing.wd1.myworkdayjobs.com/EXTERNAL_CAREERS") == "generic_portal"

    def test_workday_job_detail_is_direct_requisition(self):
        url = (
            "https://boeing.wd1.myworkdayjobs.com/EXTERNAL_CAREERS/job/Bengaluru-India/"
            "Lead-Systems-Engineer_JR12345"
        )
        assert classify_url_type(url) == "direct_requisition"

    def test_kula_board_root_is_generic_portal(self):
        assert classify_url_type("https://careers.kula.ai/sarla") == "generic_portal"

    def test_kula_specific_role_is_direct_requisition(self):
        assert classify_url_type("https://careers.kula.ai/sarla/role-id-123") == "direct_requisition"

    def test_freshteam_root_is_generic_portal(self):
        assert classify_url_type("https://sarla.freshteam.com/jobs") == "generic_portal"

    def test_freshteam_specific_role_is_direct_requisition(self):
        assert classify_url_type("https://sarla.freshteam.com/jobs/abc123/avionics-engineer") == "direct_requisition"

    def test_fragment_with_role_keyword_is_board_role_anchor(self):
        url = "https://www.greenaero.in/careers/#roles"
        assert classify_url_type(url) == "board_role_anchor"

    def test_fragment_with_openings_keyword_is_board_role_anchor(self):
        url = "https://startup.example.in/careers/#openings"
        assert classify_url_type(url) == "board_role_anchor"

    def test_fragment_unrelated_is_direct_requisition(self):
        # A fragment that doesn't match any role keyword — treated as direct_requisition
        url = "https://startup.example.in/careers/some-role-id-123#apply"
        assert classify_url_type(url) == "direct_requisition"


# ===========================================================================
# _check_ats_api_direct
# ===========================================================================

class TestCheckAtsApiDirect:
    def test_lever_api_200_returns_active(self):
        session = MagicMock()
        session.get.return_value = _mock_response(200)
        result = _check_ats_api_direct(
            "https://jobs.lever.co/acronaviation/abc-uuid-123", session, timeout=5
        )
        assert result is not None
        assert result["status"] == "active"
        assert result["is_active"] is True
        assert "Lever API" in result["reason"]

    def test_lever_api_404_returns_dead(self):
        session = MagicMock()
        session.get.return_value = _mock_response(404)
        result = _check_ats_api_direct(
            "https://jobs.lever.co/acronaviation/abc-uuid-404", session, timeout=5
        )
        assert result is not None
        assert result["status"] == "dead"
        assert result["is_active"] is False

    def test_lever_api_410_returns_dead(self):
        session = MagicMock()
        session.get.return_value = _mock_response(410)
        result = _check_ats_api_direct(
            "https://jobs.lever.co/acronaviation/gone-job", session, timeout=5
        )
        assert result["status"] == "dead"

    def test_greenhouse_api_200_returns_active(self):
        session = MagicMock()
        session.get.return_value = _mock_response(200)
        result = _check_ats_api_direct(
            "https://boards.greenhouse.io/sarla/jobs/9876543", session, timeout=5
        )
        assert result is not None
        assert result["status"] == "active"
        assert "Greenhouse API" in result["reason"]

    def test_greenhouse_api_404_returns_dead(self):
        session = MagicMock()
        session.get.return_value = _mock_response(404)
        result = _check_ats_api_direct(
            "https://boards.greenhouse.io/sarla/jobs/9876543", session, timeout=5
        )
        assert result["status"] == "dead"

    def test_non_ats_host_returns_none(self):
        session = MagicMock()
        result = _check_ats_api_direct(
            "https://careers.boeing.com/some-job", session, timeout=5
        )
        assert result is None

    def test_lever_root_only_returns_none(self):
        """Lever board root with only 1 segment should not trigger API call."""
        session = MagicMock()
        result = _check_ats_api_direct(
            "https://jobs.lever.co/acronaviation", session, timeout=5
        )
        assert result is None

    def test_request_exception_returns_none(self):
        import requests as req_lib
        session = MagicMock()
        session.get.side_effect = req_lib.RequestException("connection error")
        result = _check_ats_api_direct(
            "https://jobs.lever.co/acronaviation/abc-uuid", session, timeout=5
        )
        assert result is None


# ===========================================================================
# check_url_health
# ===========================================================================

class TestCheckUrlHealth:
    def test_missing_url_returns_missing(self):
        result = check_url_health("")
        assert result["status"] == "missing"
        assert result["is_active"] is False

    def test_generic_portal_returns_immediately(self):
        result = check_url_health("https://boeing.wd1.myworkdayjobs.com/EXTERNAL_CAREERS")
        assert result["status"] == "generic_portal"
        assert result["is_active"] is False

    def test_workday_429_is_rate_limited_never_expired(self):
        """HTTP 429 from Workday must be classified as rate_limited, NOT expired."""
        with patch("scripts.verify_links.create_http_session") as mock_session_factory:
            session = MagicMock()
            mock_session_factory.return_value = session
            # ATS API check: returns None for Workday (not Lever/Greenhouse)
            session.get.return_value = _mock_response(
                429,
                url="https://boeing.wd1.myworkdayjobs.com/EXTERNAL_CAREERS/job/Bangalore/Lead-Systems-Engineer_JR999",
            )
            url = (
                "https://boeing.wd1.myworkdayjobs.com/EXTERNAL_CAREERS/job/Bangalore/"
                "Lead-Systems-Engineer_JR999"
            )
            result = check_url_health(url, url_type="direct_requisition", session=session)
        assert result["status"] == "rate_limited", (
            f"HTTP 429 must be 'rate_limited', got '{result['status']}'"
        )
        assert result["http_code"] == 429
        assert result["is_active"] is True  # rate_limited is treated as still active

    def test_404_returns_dead(self):
        session = MagicMock()
        session.get.return_value = _mock_response(404, url="https://example.com/job/gone")
        result = check_url_health(
            "https://example.com/job/gone", url_type="direct_requisition", session=session
        )
        assert result["status"] == "dead"
        assert result["is_active"] is False

    def test_410_returns_dead(self):
        session = MagicMock()
        session.get.return_value = _mock_response(410, url="https://example.com/job/gone")
        result = check_url_health(
            "https://example.com/job/gone", url_type="direct_requisition", session=session
        )
        assert result["status"] == "dead"

    def test_403_returns_restricted(self):
        session = MagicMock()
        session.get.return_value = _mock_response(403, url="https://example.com/job/protected")
        result = check_url_health(
            "https://example.com/job/protected", url_type="direct_requisition", session=session
        )
        assert result["status"] == "restricted"
        assert result["is_active"] is True  # protected = still potentially active

    def test_999_returns_restricted(self):
        """HTTP 999 (LinkedIn anti-bot) is recorded as restricted, NOT dead."""
        session = MagicMock()
        session.get.return_value = _mock_response(999, url="https://www.linkedin.com/jobs/view/12345/")
        result = check_url_health(
            "https://www.linkedin.com/jobs/view/12345/",
            url_type="direct_requisition",
            session=session,
        )
        assert result["status"] == "restricted"
        assert result["is_active"] is True

    def test_soft_404_body_detected(self):
        body = "<html><body>The job you are looking for is no longer available.</body></html>"
        session = MagicMock()
        session.get.return_value = _mock_response(200, text=body)
        result = check_url_health(
            "https://example.com/job/stale", url_type="direct_requisition", session=session
        )
        assert result["status"] == "expired"
        assert result["is_active"] is False

    def test_soft_404_job_not_found(self):
        body = "<html><body>Job not found. Please try a different search.</body></html>"
        session = MagicMock()
        session.get.return_value = _mock_response(200, text=body)
        result = check_url_health(
            "https://example.com/job/missing", url_type="direct_requisition", session=session
        )
        assert result["status"] == "expired"

    def test_redirect_to_expired_url(self):
        session = MagicMock()
        session.get.return_value = _mock_response(200, url="https://example.com/job-not-found")
        result = check_url_health(
            "https://example.com/original-job", url_type="direct_requisition", session=session
        )
        assert result["status"] == "expired"

    def test_active_200_ok(self):
        session = MagicMock()
        session.get.return_value = _mock_response(200, text="<html>Apply Now for Lead Systems Engineer</html>")
        result = check_url_health(
            "https://example.com/job/active-role", url_type="direct_requisition", session=session
        )
        assert result["status"] == "active"
        assert result["is_active"] is True

    def test_board_role_anchor_with_title_and_cta(self):
        body = """<html><body>
        <h2>Lead Systems Engineer</h2>
        <p>We are hiring an experienced systems engineer.</p>
        <a href='mailto:careers@startup.in'>Apply Now</a>
        </body></html>"""
        session = MagicMock()
        session.get.return_value = _mock_response(200, text=body)
        result = check_url_health(
            "https://www.startup.in/careers/#roles",
            url_type="board_role_anchor",
            role_title="Lead Systems Engineer",
            session=session,
        )
        assert result["status"] == "active"
        assert result["is_active"] is True

    def test_board_role_anchor_missing_cta_returns_expired(self):
        body = "<html><body><h2>Lead Systems Engineer</h2><p>No apply button anywhere.</p></body></html>"
        session = MagicMock()
        session.get.return_value = _mock_response(200, text=body)
        result = check_url_health(
            "https://www.startup.in/careers/#roles",
            url_type="board_role_anchor",
            role_title="Lead Systems Engineer",
            session=session,
        )
        assert result["status"] == "expired"
        assert result["is_active"] is False

    def test_board_role_anchor_missing_title_returns_expired(self):
        body = """<html><body>
        <h2>Avionics Engineer</h2>
        <a href='mailto:careers@startup.in'>Apply Now</a>
        </body></html>"""
        session = MagicMock()
        session.get.return_value = _mock_response(200, text=body)
        result = check_url_health(
            "https://www.startup.in/careers/#roles",
            url_type="board_role_anchor",
            role_title="MBSE Lead Engineer",
            session=session,
        )
        assert result["status"] == "expired"

    def test_connection_error_returns_error_status(self):
        import requests as req_lib
        session = MagicMock()
        session.get.side_effect = req_lib.RequestException("timeout")
        result = check_url_health(
            "https://unreachable.example.com/job/xyz",
            url_type="direct_requisition",
            session=session,
        )
        assert result["status"] == "error"
        assert result["is_active"] is False


# ===========================================================================
# verify_board_role_cta
# ===========================================================================

class TestVerifyBoardRoleCta:
    def test_empty_html_returns_false(self):
        ok, reason = verify_board_role_cta("", "Lead Systems Engineer")
        assert ok is False

    def test_empty_title_returns_false(self):
        ok, reason = verify_board_role_cta("<html>Apply now</html>", "")
        assert ok is False

    def test_exact_title_match_with_mailto_cta(self):
        html = "<p>Lead Systems Engineer</p><a href='mailto:hr@co.in'>Apply</a>"
        ok, reason = verify_board_role_cta(html, "Lead Systems Engineer")
        assert ok is True

    def test_case_insensitive_title_match(self):
        html = "<p>LEAD SYSTEMS ENGINEER</p><a href='mailto:hr@co.in'>Apply</a>"
        ok, reason = verify_board_role_cta(html, "Lead Systems Engineer")
        assert ok is True

    def test_token_level_match_with_dashes(self):
        """Title with dashes/punctuation variations should match via token-level fallback."""
        html = "<p>Lead Systems-Engineer role available</p><form><input type='submit' value='Apply'></form>"
        ok, reason = verify_board_role_cta(html, "Lead Systems Engineer")
        assert ok is True

    def test_missing_title_returns_false_with_cta(self):
        html = "<p>Avionics Engineer available</p><a href='mailto:hr@co.in'>Apply Now</a>"
        ok, reason = verify_board_role_cta(html, "MBSE Lead")
        assert ok is False
        assert "not found" in reason.lower()

    def test_title_present_but_no_cta_returns_false(self):
        html = "<p>MBSE Lead Engineer opening</p><p>Send email somewhere</p>"
        ok, reason = verify_board_role_cta(html, "MBSE Lead Engineer")
        assert ok is False
        assert "cta" in reason.lower() or "apply" in reason.lower()

    def test_apply_now_anchor_accepted(self):
        html = "<p>Senior MBSE Architect</p><a href='https://form.link'>Apply Now</a>"
        ok, _ = verify_board_role_cta(html, "Senior MBSE Architect")
        assert ok is True

    def test_apply_button_accepted(self):
        html = "<p>Systems Engineer</p><button>Apply</button>"
        ok, _ = verify_board_role_cta(html, "Systems Engineer")
        assert ok is True

    def test_google_forms_link_accepted(self):
        html = "<p>Avionics Lead</p><a href='https://forms.gle/abc123'>Apply via Google Form</a>"
        ok, _ = verify_board_role_cta(html, "Avionics Lead")
        assert ok is True

    def test_html_entity_unescaping(self):
        html = "<p>Systems &amp; Integration Engineer</p><a href='mailto:hr@co.in'>Apply</a>"
        ok, _ = verify_board_role_cta(html, "Systems & Integration Engineer")
        assert ok is True


# ===========================================================================
# _strip_html_text
# ===========================================================================

class TestStripHtmlText:
    def test_strips_script_tags(self):
        html = "<html><script>var x = 1;</script><p>Hello World</p></html>"
        result = _strip_html_text(html)
        assert "var x" not in result
        assert "Hello World" in result

    def test_strips_style_tags(self):
        html = "<html><style>body{color:red;}</style><p>Content</p></html>"
        result = _strip_html_text(html)
        assert "color:red" not in result
        assert "Content" in result

    def test_decodes_html_entities(self):
        html = "<p>Systems &amp; Integration</p>"
        result = _strip_html_text(html)
        assert "Systems & Integration" in result


# ===========================================================================
# verify_all_openings — metadata persistence
# ===========================================================================

class TestVerifyAllOpenings:
    def test_metadata_persisted_to_openings_json(self, tmp_path):
        """verify_all_openings must write link_status, link_http_code, link_last_checked back to file."""
        openings = [
            {
                "id": "TEST-001",
                "company": "Test Corp",
                "title": "Systems Engineer",
                "apply_url": "https://jobs.lever.co/testco/uuid-001",
                "url_type": "direct_requisition",
                "status": "Not Applied",
            }
        ]
        openings_file = tmp_path / "openings.json"
        openings_file.write_text(json.dumps(openings), encoding="utf-8")

        with patch("scripts.verify_links.create_http_session") as mock_sf, \
             patch("scripts.verify_links._check_ats_api_direct") as mock_ats:
            mock_ats.return_value = {
                "status": "active",
                "http_code": 200,
                "final_url": "https://jobs.lever.co/testco/uuid-001",
                "reason": "Verified via Lever API",
                "is_active": True,
            }
            mock_sf.return_value = MagicMock()
            results = verify_all_openings(
                openings_path=openings_file,
                save_updates=True,
                delay=0,
            )

        updated = json.loads(openings_file.read_text(encoding="utf-8"))
        assert updated[0]["link_status"] == "active"
        assert updated[0]["link_http_code"] == 200
        assert "link_last_checked" in updated[0]
        assert results["active"] == 1

    def test_rate_limited_counted_separately_not_as_dead(self, tmp_path):
        """Workday 429 must increment rate_limited, not dead."""
        openings = [
            {
                "id": "BOEING-JR999",
                "company": "Boeing India",
                "title": "Lead Systems Engineer",
                "apply_url": (
                    "https://boeing.wd1.myworkdayjobs.com/EXTERNAL_CAREERS/job/"
                    "Bangalore/Lead-Systems-Engineer_JR999"
                ),
                "url_type": "direct_requisition",
                "status": "Not Applied",
            }
        ]
        openings_file = tmp_path / "openings.json"
        openings_file.write_text(json.dumps(openings), encoding="utf-8")

        fake_session = MagicMock()
        fake_session.get.return_value = _mock_response(
            429,
            url="https://boeing.wd1.myworkdayjobs.com/EXTERNAL_CAREERS/job/Bangalore/Lead-Systems-Engineer_JR999",
        )

        with patch("scripts.verify_links.create_http_session", return_value=fake_session), \
             patch("scripts.verify_links._check_ats_api_direct", return_value=None):
            results = verify_all_openings(
                openings_path=openings_file,
                save_updates=True,
                delay=0,
            )

        assert results["rate_limited"] == 1, "HTTP 429 must be counted as rate_limited, not dead"
        assert results["dead"] == 0, "HTTP 429 must NOT be counted as dead"

    def test_inactive_posting_skipped_with_flag(self, tmp_path):
        openings = [
            {
                "id": "OLD-001",
                "company": "Old Corp",
                "title": "Stale Role",
                "apply_url": "https://example.com/jobs/stale",
                "url_type": "direct_requisition",
                "status": "Inactive Posting",
            }
        ]
        openings_file = tmp_path / "openings.json"
        openings_file.write_text(json.dumps(openings), encoding="utf-8")

        with patch("scripts.verify_links.create_http_session") as mock_sf:
            mock_sf.return_value = MagicMock()
            results = verify_all_openings(
                openings_path=openings_file,
                save_updates=False,
                delay=0,
                skip_inactive=True,
            )

        # With skip_inactive=True the role is entirely skipped — counters stay at 0
        assert results["active"] == 0
        assert results["dead"] == 0

    def test_missing_openings_file_returns_zero_summary(self, tmp_path):
        result = verify_all_openings(
            openings_path=tmp_path / "nonexistent.json",
            save_updates=False,
        )
        assert result["total"] == 0


# ===========================================================================
# ingest_openings url_type gate (via search_engine)
# ===========================================================================

class TestIngestUrlTypeGate:
    """Verify search_engine.ingest_openings rejects generic_portal and unverified board_role_anchor."""

    def test_generic_portal_rejected_during_ingest(self, tmp_path):
        from scripts.search_engine import ingest_openings

        openings_file = tmp_path / "openings.json"
        openings_file.write_text("[]", encoding="utf-8")
        tracker_file = tmp_path / "tracker.md"
        tracker_file.write_text("", encoding="utf-8")

        # Role with generic_portal url_type should be rejected
        role = {
            "id": "GEN-001",
            "company": "Generic Corp",
            "title": "Systems Engineer",
            "apply_url": "https://genericcorp.com/careers",
            "url_type": "generic_portal",
            "fit_score": 4.0,
            "passed_gate": True,
            "status": "Not Applied",
            "date_discovered": "2026-01-01",
        }

        result = ingest_openings([role], json_path=openings_file, md_path=tracker_file)
        assert len(result) == 0, "generic_portal roles must be rejected by ingest_openings"

    def test_direct_requisition_accepted_during_ingest(self, tmp_path):
        from scripts.search_engine import ingest_openings

        openings_file = tmp_path / "openings.json"
        openings_file.write_text("[]", encoding="utf-8")
        tracker_file = tmp_path / "tracker.md"
        tracker_file.write_text("", encoding="utf-8")

        role = {
            "id": "AIRBUS-JR12345",
            "company": "Airbus India",
            "title": "MBSE Lead Engineer",
            "apply_url": "https://ag.wd3.myworkdayjobs.com/Airbus/job/Bangalore/MBSE-Lead_JR12345",
            "url_type": "direct_requisition",
            "fit_score": 4.5,
            "passed_gate": True,
            "status": "Not Applied",
            "date_discovered": "2026-01-01",
            "last_updated": "2026-01-01",
            "location": "Bengaluru, India",
            "seniority": "Lead",
            "source": "Workday ATS",
            "req_id": "JR12345",
        }

        result = ingest_openings([role], json_path=openings_file, md_path=tracker_file)
        assert len(result) == 1, "direct_requisition roles must be accepted by ingest_openings"
