"""Integration tests for the Runbook and Agent Operating Manual."""

import subprocess
import sys
from pathlib import Path


def test_cli_dry_run_pipeline():
    """Verify that the CLI notifier dry run pipeline executes successfully."""
    result = subprocess.run(
        [sys.executable, "scripts/notifier.py", "--dry-run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Digest Preview" in result.stdout or "No new roles" in result.stdout


def test_cli_runbook_commands():
    """Verify that all core CLI utilities referenced in README and GEMINI respond correctly."""
    # sync_tracker
    res_sync = subprocess.run(
        [sys.executable, "scripts/sync_tracker.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert res_sync.returncode == 0
    assert "--to-md" in res_sync.stdout

    # scorer
    res_scorer = subprocess.run(
        [sys.executable, "scripts/scorer.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert res_scorer.returncode == 0

    # search_engine
    res_search = subprocess.run(
        [sys.executable, "scripts/search_engine.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert res_search.returncode == 0
    assert "--queries" in res_search.stdout
    assert "--scan-ats" in res_search.stdout


def test_gemini_operating_manual_contents():
    """Verify GEMINI.md exists and covers candidate profile, rules, safety, commands, and automation."""
    gemini_path = Path("GEMINI.md")
    assert gemini_path.exists(), "GEMINI.md must exist in repository root"
    content = gemini_path.read_text(encoding="utf-8")

    # Profile summary
    assert "Mansi Agrawal" in content
    assert "Boeing" in content
    assert "Georgia Tech" in content
    assert "MBSE" in content
    assert "Bangalore" in content

    # Operating rules & gates
    assert "fit_score" in content or "Fit Score" in content
    assert "Openings_Tracker.md" in content or "openings.json" in content
    assert "agrawal.mansi20@gmail.com" in content

    # LinkedIn safety envelope
    assert "250" in content and "600" in content  # 250-600px scroll
    assert "2" in content and "6" in content      # 2-6s pauses
    assert "30" in content or "50" in content     # 30-50 views/day
    assert "15" in content and "20" in content    # 15m on / 20m off

    # Agent slash commands
    assert "/discover" in content
    assert "/sync" in content
    assert "/digest" in content
    assert "/email" in content

    # Antigravity automation schedule
    assert "schedule" in content.lower() or "automation" in content.lower()


def test_readme_runbook_contents():
    """Verify README.md exists and contains human operator instructions."""
    readme_path = Path("README.md")
    assert readme_path.exists(), "README.md must exist in repository root"
    content = readme_path.read_text(encoding="utf-8")

    # Architecture & directory structure
    assert "Architecture" in content or "Overview" in content
    assert "scripts/" in content
    assert "data/" in content
    assert "profile/" in content

    # Quickstart and CLI execution
    assert "Quick Start" in content or "Getting Started" in content
    assert "scripts/notifier.py" in content
    assert "pytest" in content
