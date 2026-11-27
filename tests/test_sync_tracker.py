import json
import shutil
import subprocess
import sys
from pathlib import Path
from scripts.sync_tracker import sync_json_to_markdown, sync_markdown_to_json


def test_sync_json_to_markdown(tmp_path):
    json_file = tmp_path / "openings.json"
    md_file = tmp_path / "Openings_Tracker.md"
    sample = [{
        "id": "AIRBUS-1",
        "company": "Airbus India",
        "team": "Systems",
        "title": "MBSE Leader",
        "location": "Bangalore",
        "req_id": "JR100",
        "seniority": "Lead",
        "fit_score": 5,
        "fit_rationale": "Direct match",
        "skills_matched": ["MBSE"],
        "apply_url": "https://example.com",
        "source": "Workday",
        "status": "Not Applied",
        "date_discovered": "2026-11-24",
        "last_updated": "2026-11-24",
        "next_action": "Apply"
    }]
    json_file.write_text(json.dumps(sample, indent=2))
    sync_json_to_markdown(json_file, md_file)
    content = md_file.read_text()
    assert "| Company | Team | Role | Location | Req ID | Seniority | Fit | Status | Link | Next Action |" in content
    assert "| Airbus India | Systems | MBSE Leader | Bangalore | JR100 | Lead | 5 | Not Applied | [Apply](https://example.com) | Apply |" in content


def test_sync_markdown_to_json_updates_and_preserves_metadata(tmp_path):
    json_file = tmp_path / "openings.json"
    md_file = tmp_path / "Openings_Tracker.md"
    sample = [{
        "id": "AIRBUS-1",
        "company": "Airbus India",
        "team": "Systems",
        "title": "MBSE Leader",
        "location": "Bangalore",
        "req_id": "JR100",
        "seniority": "Lead",
        "fit_score": 5,
        "fit_rationale": "Direct match",
        "skills_matched": ["MBSE", "Cameo"],
        "apply_url": "https://example.com",
        "source": "Workday",
        "status": "Not Applied",
        "date_discovered": "2026-11-20",
        "last_updated": "2026-11-20",
        "next_action": "Apply"
    }]
    json_file.write_text(json.dumps(sample, indent=2))
    sync_json_to_markdown(json_file, md_file)

    # User modifies status in Markdown to "Applied" and updates Next Action
    md_content = md_file.read_text()
    modified_md = md_content.replace(
        "| Not Applied | [Apply](https://example.com) | Apply |",
        "| Applied | [Apply](https://example.com) | Follow up with recruiter |"
    )
    md_file.write_text(modified_md)

    # Sync back to JSON
    sync_markdown_to_json(md_file, json_file)

    updated_json = json.loads(json_file.read_text())
    assert len(updated_json) == 1
    item = updated_json[0]
    assert item["id"] == "AIRBUS-1"
    assert item["company"] == "Airbus India"
    assert item["status"] == "Applied"
    assert item["next_action"] == "Follow up with recruiter"
    assert item["skills_matched"] == ["MBSE", "Cameo"]
    assert item["fit_rationale"] == "Direct match"
    assert item["source"] == "Workday"
    assert item["date_discovered"] == "2026-11-20"


def test_sync_markdown_to_json_new_entry(tmp_path):
    json_file = tmp_path / "openings.json"
    md_file = tmp_path / "Openings_Tracker.md"
    json_file.write_text("[]")

    md_content = """# Job Openings Tracker

| Company | Team | Role | Location | Req ID | Seniority | Fit | Status | Link | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Collins Aerospace | Avionics | Senior Systems Engineer | Bangalore | 12345 | Senior | 4 | Not Applied | [Apply](https://collins.com/job/12345) | Tailor resume |
"""
    md_file.write_text(md_content)
    sync_markdown_to_json(md_file, json_file)

    updated_json = json.loads(json_file.read_text())
    assert len(updated_json) == 1
    item = updated_json[0]
    assert item["company"] == "Collins Aerospace"
    assert item["team"] == "Avionics"
    assert item["title"] == "Senior Systems Engineer"
    assert item["location"] == "Bangalore"
    assert item["req_id"] == "12345"
    assert item["seniority"] == "Senior"
    assert item["fit_score"] == 4
    assert item["status"] == "Not Applied"
    assert item["apply_url"] == "https://collins.com/job/12345"
    assert item["next_action"] == "Tailor resume"
    assert "id" in item and item["id"]


def test_cli_execution(tmp_path):
    json_file = tmp_path / "openings.json"
    md_file = tmp_path / "Openings_Tracker.md"
    sample = [{
        "id": "BOEING-1",
        "company": "Boeing",
        "team": "Avionics",
        "title": "Systems Lead",
        "location": "Bangalore",
        "req_id": "B123",
        "seniority": "Lead",
        "fit_score": 5,
        "fit_rationale": "Top fit",
        "skills_matched": ["MBSE"],
        "apply_url": "https://boeing.com/job",
        "source": "Official",
        "status": "Not Applied",
        "date_discovered": "2026-11-24",
        "last_updated": "2026-11-24",
        "next_action": "Apply"
    }]
    json_file.write_text(json.dumps(sample, indent=2))

    # Test CLI --to-md
    site_file = tmp_path / "index.html"
    res = subprocess.run([
        sys.executable, "scripts/sync_tracker.py",
        "--to-md",
        "--json-path", str(json_file),
        "--md-path", str(md_file),
        "--site-output", str(site_file),
    ], capture_output=True, text=True)
    assert res.returncode == 0
    assert md_file.exists()
    assert site_file.exists()
    assert "Boeing" in md_file.read_text()

    # Modify markdown and test CLI --to-json
    content = md_file.read_text().replace("Not Applied", "Applied")
    md_file.write_text(content)

    res = subprocess.run([
        sys.executable, "scripts/sync_tracker.py",
        "--to-json",
        "--json-path", str(json_file),
        "--md-path", str(md_file),
        "--site-output", str(site_file),
    ], capture_output=True, text=True)
    assert res.returncode == 0
    updated = json.loads(json_file.read_text())
    assert updated[0]["status"] == "Applied"


def test_real_tracker_roundtrip(tmp_path):
    real_json = Path("data/openings.json")
    if not real_json.exists():
        return

    tmp_json = tmp_path / "openings.json"
    tmp_md = tmp_path / "Openings_Tracker.md"
    shutil.copy(real_json, tmp_json)

    # JSON -> MD
    sync_json_to_markdown(tmp_json, tmp_md)
    assert tmp_md.exists()

    # MD -> JSON
    sync_markdown_to_json(tmp_md, tmp_json)

    orig = json.loads(real_json.read_text(encoding="utf-8"))
    synced = json.loads(tmp_json.read_text(encoding="utf-8"))

    assert len(orig) == len(synced)
    for o, s in zip(orig, synced):
        assert o["id"] == s["id"]
        assert o["company"] == s["company"]
        assert o["title"] == s["title"]
        assert o["location"] == s["location"]
        assert o["req_id"] == s["req_id"]
        assert o["seniority"] == s["seniority"]
        assert o["fit_score"] == s["fit_score"]
        assert o["status"] == s["status"]
        assert o["apply_url"] == s["apply_url"]
        assert o["next_action"] == s["next_action"]
        assert o["skills_matched"] == s["skills_matched"]
        assert o["fit_rationale"] == s["fit_rationale"]
