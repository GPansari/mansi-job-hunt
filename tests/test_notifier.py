import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from scripts.notifier import (
    archive_digest,
    dispatch_email,
    filter_unnotified_roles,
    generate_digest,
    load_sent_history,
    main,
    save_sent_history,
)


def test_filter_unnotified_roles():
    history = {"AIRBUS-JR10400715"}
    openings = [
        {"id": "AIRBUS-JR10400715", "fit_score": 5},
        {"id": "RTX-01868963", "fit_score": 5},
        {"id": "LOW-FIT-1", "fit_score": 2},
    ]
    unnotified = filter_unnotified_roles(openings, history, min_fit_score=3)
    assert len(unnotified) == 1
    assert unnotified[0]["id"] == "RTX-01868963"


def test_filter_unnotified_roles_edge_cases():
    assert filter_unnotified_roles([], set()) == []
    
    # Missing or invalid fit scores
    openings = [
        {"id": "VALID-1", "fit_score": "4"},  # String representation of int
        {"id": "VALID-2", "fit_score": 3.5},
        {"id": "NO-FIT"},
        {"id": "BAD-FIT", "fit_score": "invalid"},
        {"fit_score": 5},  # Missing id
    ]
    filtered = filter_unnotified_roles(openings, set(), min_fit_score=3)
    ids = [r.get("id") for r in filtered]
    assert "VALID-1" in ids
    assert "VALID-2" in ids
    assert "NO-FIT" not in ids
    assert "BAD-FIT" not in ids
    assert None not in ids

    # History as list or None
    assert len(filter_unnotified_roles([{"id": "A", "fit_score": 4}], None)) == 1
    assert len(filter_unnotified_roles([{"id": "A", "fit_score": 4}], ["A"])) == 0


def test_generate_digest_content():
    roles = [{
        "id": "RTX-01868963",
        "company": "Collins Aerospace",
        "title": "Lead Engineer - DEMPA",
        "location": "Bangalore",
        "fit_score": 5,
        "skills_matched": ["Cameo", "SysML", "MATLAB"],
        "apply_url": "https://example.com/rtx",
        "next_action": "Draft tailored resume",
    }]
    text, html = generate_digest(roles, candidate_name="Mansi")
    assert "Collins Aerospace" in text
    assert "https://example.com/rtx" in text
    assert "<html>" in html
    assert "Collins Aerospace" in html
    assert "Mansi" in text
    assert "Mansi" in html
    assert "Cameo" in text
    assert "Cameo" in html
    assert "Draft tailored resume" in text
    assert "https://example.com/rtx" in html


def test_generate_digest_empty():
    text, html = generate_digest([], candidate_name="Mansi")
    assert "Mansi" in text
    assert "No new matching roles" in text or "0 new" in text.lower() or "no roles" in text.lower()
    assert "<html>" in html


def test_load_and_save_sent_history(tmp_path):
    history_file = tmp_path / "sent_history.json"
    
    # Non-existent file returns empty set
    assert load_sent_history(history_file) == set()

    # Save and reload
    save_sent_history({"ROLE-1", "ROLE-2"}, history_file)
    loaded = load_sent_history(history_file)
    assert loaded == {"ROLE-1", "ROLE-2"}

    # Corrupt file returns empty set safely
    history_file.write_text("{bad json")
    assert load_sent_history(history_file) == set()


def test_archive_digest(tmp_path):
    digest_dir = tmp_path / "reports"
    digest_path = archive_digest("<html><body>Test Digest</body></html>", digest_dir=digest_dir, date_str="2026-11-24")
    assert digest_path.exists()
    assert digest_path.name == "2026-11-24-digest.html"
    assert "Test Digest" in digest_path.read_text()


def test_dispatch_email_dry_run(tmp_path, capsys):
    history_file = tmp_path / "sent_history.json"
    with patch("subprocess.run") as mock_run:
        success = dispatch_email(
            recipient="agrawal.mansi20@gmail.com",
            subject="Weekly Digest",
            text_body="Preview Body",
            html_body="<html>Preview</html>",
            dry_run=True,
            role_ids=["ROLE-1"],
            history_file=history_file,
            digest_dir=tmp_path / "reports",
        )
        assert success is True
        mock_run.assert_not_called()
        assert not history_file.exists()


def test_dispatch_email_send_success(tmp_path):
    history_file = tmp_path / "sent_history.json"
    digest_dir = tmp_path / "reports"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="Email sent successfully", stderr="")
        
        success = dispatch_email(
            recipient="agrawal.mansi20@gmail.com",
            subject="Weekly Digest",
            text_body="Hello Plain Text",
            html_body="<html><body>Hello HTML</body></html>",
            dry_run=False,
            role_ids=["ROLE-100", "ROLE-200"],
            history_file=history_file,
            digest_dir=digest_dir,
            date_str="2026-11-24",
        )

        assert success is True
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "gmail"
        assert call_args[1] == "mutate"
        assert call_args[2] == "send"
        assert "--to" in call_args
        assert "agrawal.mansi20@gmail.com" in call_args
        assert "--subject" in call_args
        assert "--html-file" in call_args
        assert "--body-file" in call_args

        # Verify environment has AGY_ACCOUNT
        env = mock_run.call_args[1].get("env", {})
        assert env.get("AGY_ACCOUNT") == "imgauravpansari@gmail.com"

        # Verify sent history is recorded
        saved_history = load_sent_history(history_file)
        assert "ROLE-100" in saved_history
        assert "ROLE-200" in saved_history

        # Verify archive digest was written
        archived = digest_dir / "2026-11-24-digest.html"
        assert archived.exists()
        assert "Hello HTML" in archived.read_text()


def test_dispatch_email_send_failure(tmp_path):
    history_file = tmp_path / "sent_history.json"
    digest_dir = tmp_path / "reports"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Authentication failed")
        
        success = dispatch_email(
            recipient="agrawal.mansi20@gmail.com",
            subject="Weekly Digest",
            text_body="Hello Plain Text",
            html_body="<html><body>Hello HTML</body></html>",
            dry_run=False,
            role_ids=["ROLE-100"],
            history_file=history_file,
            digest_dir=digest_dir,
        )

        assert success is False
        # Since send failed, history must NOT contain the unsent role
        assert load_sent_history(history_file) == set()


def test_cli_dry_run_flag(tmp_path, capsys):
    openings = [
        {
            "id": "AIRBUS-1",
            "company": "Airbus",
            "title": "Systems Lead",
            "location": "Bangalore",
            "fit_score": 5,
            "skills_matched": ["MBSE"],
            "apply_url": "https://airbus.com",
            "next_action": "Apply",
        }
    ]
    openings_path = tmp_path / "openings.json"
    openings_path.write_text(json.dumps(openings))
    history_path = tmp_path / "history.json"

    with patch("sys.argv", [
        "notifier.py",
        "--openings", str(openings_path),
        "--history", str(history_path),
        "--dry-run",
    ]):
        exit_code = main()
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "Digest Preview" in captured
        assert "Airbus" in captured
        assert not history_path.exists()


def test_cli_no_new_roles(tmp_path, capsys):
    openings = [{"id": "OLD-1", "fit_score": 5}]
    openings_path = tmp_path / "openings.json"
    openings_path.write_text(json.dumps(openings))
    history_path = tmp_path / "history.json"
    history_path.write_text(json.dumps(["OLD-1"]))

    with patch("sys.argv", [
        "notifier.py",
        "--openings", str(openings_path),
        "--history", str(history_path),
        "--dry-run",
    ]):
        exit_code = main()
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "No new roles" in captured


def test_cli_dry_run_pipeline():
    import sys
    import subprocess
    result = subprocess.run([
        sys.executable, "scripts/notifier.py", "--dry-run"
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Digest Preview" in result.stdout or "No new roles" in result.stdout

