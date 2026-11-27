"""Unit tests for scripts/run_pipeline.py.

Covers:
  - run_pipeline() dry-run orchestration: all 5 stages called in sequence
  - tracker_synced and site_rebuilt flags set True on success
  - email_dispatched stays False in dry-run mode
  - non-zero exit (return code 1) on critical stage failure
  - missing companies file raises FileNotFoundError (halts pipeline)
  - skip_discovery and skip_verify flags bypass respective stages
  - main() CLI: --dry-run default, --send opt-in, --skip-discovery, --skip-verify
  - summary dict keys and types are correct
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_pipeline import main, run_pipeline


# ===========================================================================
# Helpers / fixtures
# ===========================================================================

def _make_minimal_files(tmp_path: Path) -> dict[str, Path]:
    """Create minimal valid test data files for pipeline tests."""
    companies = [
        {
            "name": "Test ATS Corp",
            "relevance": 5,
            "careers_url": "https://jobs.lever.co/testco",
            "ats_type": "lever",
            "lever_site": "testco",
            "tier": "Enterprise / OEM",
            "location": "Bengaluru, India",
        }
    ]
    openings: list = []
    candidate = {
        "name": "Mansi Agrawal",
        "target_roles": ["Lead Systems Engineer"],
        "skills": ["MBSE", "SysML", "Cameo"],
        "target_locations": ["Bengaluru"],
        "disqualify_keywords": ["intern", "frontend"],
    }
    history: dict = {"sent_role_ids": []}

    companies_file = tmp_path / "target_companies.json"
    companies_file.write_text(json.dumps(companies), encoding="utf-8")
    openings_file = tmp_path / "openings.json"
    openings_file.write_text(json.dumps(openings), encoding="utf-8")
    tracker_file = tmp_path / "Openings_Tracker.md"
    tracker_file.write_text("", encoding="utf-8")
    candidate_file = tmp_path / "candidate.json"
    candidate_file.write_text(json.dumps(candidate), encoding="utf-8")
    site_file = tmp_path / "index.html"
    history_file = tmp_path / "sent_history.json"
    history_file.write_text(json.dumps(history), encoding="utf-8")

    return {
        "companies": companies_file,
        "openings": openings_file,
        "tracker": tracker_file,
        "candidate": candidate_file,
        "site": site_file,
        "history": history_file,
    }


def _make_pipeline_mocks():
    """Return a dict of patch targets (bare attr names) for use with patch.multiple."""
    return {
        "load_candidate_profile": MagicMock(return_value={"name": "Mansi"}),
        "scan_all_ats_feeds": MagicMock(return_value=[]),
        "ingest_openings": MagicMock(return_value=[]),
        "verify_all_openings": MagicMock(
            return_value={"total": 0, "active": 0, "dead": 0, "restricted": 0, "rate_limited": 0}
        ),
        "sync_json_to_markdown": MagicMock(),
        "build_site": MagicMock(),
        "load_sent_history": MagicMock(return_value={"sent_role_ids": []}),
        "filter_unnotified_roles": MagicMock(return_value=[]),
        "generate_digest": MagicMock(return_value=("text", "<html>html</html>")),
        "dispatch_email": MagicMock(return_value=True),
    }


# ===========================================================================
# run_pipeline() unit tests
# ===========================================================================

class TestRunPipeline:
    def test_dry_run_completes_all_stages(self, tmp_path):
        """All 5 pipeline stages must execute; tracker_synced and site_rebuilt must be True."""
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()

        with patch.multiple("scripts.run_pipeline", **mocks):
            summary = run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
                send_email=False,
                skip_discovery=False,
                skip_verify=False,
            )

        assert summary["tracker_synced"] is True
        assert summary["site_rebuilt"] is True
        assert summary["dry_run"] is True
        assert summary["email_dispatched"] is False

    def test_summary_has_required_keys(self, tmp_path):
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()

        with patch.multiple("scripts.run_pipeline", **mocks):
            summary = run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
            )

        for key in ("started_at", "finished_at", "discovered_total", "ingested_count",
                    "tracker_synced", "site_rebuilt", "unnotified_count", "email_dispatched", "dry_run"):
            assert key in summary, f"Summary missing key: {key}"

    def test_scan_all_ats_feeds_called_once(self, tmp_path):
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()

        with patch.multiple("scripts.run_pipeline", **mocks):
            run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
                skip_discovery=False,
                skip_verify=True,
            )

        mocks["scan_all_ats_feeds"].assert_called_once()

    def test_skip_discovery_bypasses_ats_scan(self, tmp_path):
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()

        with patch.multiple("scripts.run_pipeline", **mocks):
            run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
                skip_discovery=True,
                skip_verify=True,
            )

        mocks["scan_all_ats_feeds"].assert_not_called()

    def test_skip_verify_bypasses_link_audit(self, tmp_path):
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()

        with patch.multiple("scripts.run_pipeline", **mocks):
            run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
                skip_discovery=True,
                skip_verify=True,
            )

        mocks["verify_all_openings"].assert_not_called()

    def test_sync_tracker_always_called(self, tmp_path):
        """sync_json_to_markdown must be called even when discovery and verify are skipped."""
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()

        with patch.multiple("scripts.run_pipeline", **mocks):
            run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
                skip_discovery=True,
                skip_verify=True,
            )

        mocks["sync_json_to_markdown"].assert_called_once_with(
            files["openings"], files["tracker"]
        )

    def test_build_site_always_called(self, tmp_path):
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()

        with patch.multiple("scripts.run_pipeline", **mocks):
            run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
                skip_discovery=True,
                skip_verify=True,
            )

        mocks["build_site"].assert_called_once()

    def test_missing_companies_file_raises(self, tmp_path):
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()
        # Remove companies file to trigger FileNotFoundError
        files["companies"].unlink()

        with patch.multiple("scripts.run_pipeline", **mocks), \
             pytest.raises(FileNotFoundError, match="target_companies"):
            run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],  # doesn't exist now
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
                skip_discovery=False,
                skip_verify=True,
            )

    def test_no_unnotified_roles_skips_email(self, tmp_path):
        """When filter_unnotified_roles returns [], email must not be dispatched."""
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()
        mocks["filter_unnotified_roles"].return_value = []

        with patch.multiple("scripts.run_pipeline", **mocks):
            summary = run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
                send_email=True,
                skip_discovery=True,
                skip_verify=True,
            )

        mocks["dispatch_email"].assert_not_called()
        assert summary["email_dispatched"] is False

    def test_send_email_true_dispatches_email(self, tmp_path):
        """With send_email=True and unnotified roles, dispatch_email must be called."""
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()
        unnotified_role = {
            "id": "TEST-001",
            "company": "Sarla Aviation",
            "title": "Lead Systems Engineer",
            "fit_score": 4.5,
            "apply_url": "https://jobs.lever.co/sarla/abc",
            "status": "Not Applied",
        }
        mocks["filter_unnotified_roles"].return_value = [unnotified_role]

        with patch.multiple("scripts.run_pipeline", **mocks):
            summary = run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
                send_email=True,
                skip_discovery=True,
                skip_verify=True,
            )

        mocks["dispatch_email"].assert_called_once()
        assert summary["email_dispatched"] is True

    def test_dispatch_email_false_in_dry_run_with_roles(self, tmp_path):
        """Even when unnotified roles exist, dry_run must NOT set email_dispatched=True."""
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()
        mocks["filter_unnotified_roles"].return_value = [
            {"id": "TEST-002", "company": "AeroCorp", "title": "MBSE Lead", "fit_score": 4.0,
             "apply_url": "https://example.com/job", "status": "Not Applied"}
        ]

        with patch.multiple("scripts.run_pipeline", **mocks):
            summary = run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
                send_email=False,  # dry-run
                skip_discovery=True,
                skip_verify=True,
            )

        assert summary["email_dispatched"] is False
        assert summary["dry_run"] is True

    def test_link_audit_summary_populated(self, tmp_path):
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()
        mocks["verify_all_openings"].return_value = {
            "total": 10,
            "active": 7,
            "dead": 2,
            "restricted": 1,
            "rate_limited": 0,
        }

        with patch.multiple("scripts.run_pipeline", **mocks):
            summary = run_pipeline(
                openings_path=files["openings"],
                tracker_path=files["tracker"],
                companies_path=files["companies"],
                candidate_path=files["candidate"],
                site_output_path=files["site"],
                history_path=files["history"],
                skip_discovery=True,
                skip_verify=False,
            )

        assert summary["link_audit"] is not None
        assert summary["link_audit"]["total"] == 10
        assert summary["link_audit"]["active"] == 7
        assert summary["link_audit"]["dead"] == 2


# ===========================================================================
# main() CLI entry point
# ===========================================================================

class TestRunPipelineMain:
    def test_main_dry_run_returns_zero(self, tmp_path):
        """main() with --dry-run must return 0 on success."""
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()

        with patch.multiple("scripts.run_pipeline", **mocks):
            rc = main([
                "--dry-run",
                "--skip-discovery",
                "--skip-verify",
                "--openings", str(files["openings"]),
                "--tracker", str(files["tracker"]),
                "--companies", str(files["companies"]),
                "--candidate", str(files["candidate"]),
                "--output", str(files["site"]),
                "--history", str(files["history"]),
            ])

        assert rc == 0

    def test_main_send_flag_dispatches_email(self, tmp_path):
        """main() with --send must call dispatch_email (send_email=True)."""
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()
        mocks["filter_unnotified_roles"].return_value = [
            {"id": "SEND-001", "company": "Corp", "title": "Role", "fit_score": 4.0,
             "apply_url": "https://example.com/job", "status": "Not Applied"}
        ]

        with patch.multiple("scripts.run_pipeline", **mocks):
            rc = main([
                "--send",
                "--skip-discovery",
                "--skip-verify",
                "--openings", str(files["openings"]),
                "--tracker", str(files["tracker"]),
                "--companies", str(files["companies"]),
                "--candidate", str(files["candidate"]),
                "--output", str(files["site"]),
                "--history", str(files["history"]),
            ])

        assert rc == 0
        mocks["dispatch_email"].assert_called_once()

    def test_main_returns_1_on_critical_failure(self, tmp_path):
        """main() must return exit code 1 when pipeline raises an exception."""
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()
        mocks["sync_json_to_markdown"].side_effect = RuntimeError("sync failed")

        with patch.multiple("scripts.run_pipeline", **mocks):
            rc = main([
                "--dry-run",
                "--skip-discovery",
                "--skip-verify",
                "--openings", str(files["openings"]),
                "--tracker", str(files["tracker"]),
                "--companies", str(files["companies"]),
                "--candidate", str(files["candidate"]),
                "--output", str(files["site"]),
                "--history", str(files["history"]),
            ])

        assert rc == 1

    def test_main_skip_discovery_flag(self, tmp_path):
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()

        with patch.multiple("scripts.run_pipeline", **mocks):
            main([
                "--dry-run",
                "--skip-discovery",
                "--skip-verify",
                "--openings", str(files["openings"]),
                "--tracker", str(files["tracker"]),
                "--companies", str(files["companies"]),
                "--candidate", str(files["candidate"]),
                "--output", str(files["site"]),
                "--history", str(files["history"]),
            ])

        mocks["scan_all_ats_feeds"].assert_not_called()

    def test_main_skip_verify_flag(self, tmp_path):
        files = _make_minimal_files(tmp_path)
        mocks = _make_pipeline_mocks()

        with patch.multiple("scripts.run_pipeline", **mocks):
            main([
                "--dry-run",
                "--skip-discovery",
                "--skip-verify",
                "--openings", str(files["openings"]),
                "--tracker", str(files["tracker"]),
                "--companies", str(files["companies"]),
                "--candidate", str(files["candidate"]),
                "--output", str(files["site"]),
                "--history", str(files["history"]),
            ])

        mocks["verify_all_openings"].assert_not_called()
