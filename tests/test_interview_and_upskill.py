import json
from pathlib import Path

import pytest

from scripts.interview_prep import generate_interview_prep, main as interview_prep_main
from scripts.upskill_analyzer import (
    aggregate_skill_gaps,
    main as upskill_main,
    write_upskill_report,
)


def test_generate_interview_prep_creates_grounded_pack(tmp_path):
    app_dir = tmp_path / "AIRBUS-JR10437140"
    app_dir.mkdir(parents=True)
    (app_dir / "analysis.json").write_text(
        json.dumps(
            {
                "opening_id": "AIRBUS-JR10437140",
                "company": "Airbus India",
                "title": "Modelling and Simulation Systems Engineering",
                "matched_skills": ["MBSE", "SysML"],
                "skill_gaps": ["Polarion"],
                "matched_standards": ["ARP4754A"],
                "priority_keywords": ["MBSE", "SysML"],
            }
        ),
        encoding="utf-8",
    )
    out_path = generate_interview_prep("AIRBUS-JR10437140", applications_dir=tmp_path)
    content = out_path.read_text(encoding="utf-8")
    assert out_path == app_dir / "interview_prep.md"
    assert "Airbus India" in content
    assert "Boeing" in content
    assert "Polarion" in content
    for section in (
        "## Role Snapshot",
        "## Technical Deep-Dive Topics",
        "## Grounded STAR Story Bank",
        "## Gap Mitigation Talking Points",
        "## Questions for the Interview Panel",
    ):
        assert section in content


def test_generate_interview_prep_synthesizes_when_analysis_missing(tmp_path):
    out_path = generate_interview_prep("RTX-01889489", applications_dir=tmp_path)
    content = out_path.read_text(encoding="utf-8")
    assert out_path == tmp_path / "RTX-01889489" / "interview_prep.md"
    assert "Collins Aerospace (RTX)" in content
    assert "Principal Engineer" in content
    assert "Boeing India" in content
    assert "## Grounded STAR Story Bank" in content
    assert "777-8F" in content


def test_build_deep_dive_topics_attributes_topsis_to_eco_modular_without_double_parens():
    from scripts.interview_prep import _build_deep_dive_topics
    from scripts.profile_loader import load_master_profile

    profile = load_master_profile()
    topics = _build_deep_dive_topics(
        matched_skills=["UAV", "MBSE"],
        matched_standards=["ARP4754A"],
        priority_keywords=["UAV"],
        verified_facts=profile["verified_facts"],
    )
    uav_topic = next(t for t in topics if "UAV Sizing & Trade Studies" in t)
    assert "Eco-Modular Aircraft" in uav_topic
    assert "TOPSIS" in uav_topic
    assert ") (" not in uav_topic
    assert "((" not in uav_topic
    assert "))" not in uav_topic


def test_generate_interview_prep_rejects_invalid_and_unknown_ids(tmp_path):
    with pytest.raises(ValueError, match="Invalid opening_id"):
        generate_interview_prep("../escape", applications_dir=tmp_path)

    with pytest.raises(KeyError):
        generate_interview_prep("NONEXISTENT-999999", applications_dir=tmp_path)


def test_interview_prep_cli_entrypoint(tmp_path, capsys):
    exit_code = interview_prep_main(
        ["--id", "AIRBUS-JR10437140", "--applications-dir", str(tmp_path)]
    )
    assert exit_code == 0
    out_path = tmp_path / "AIRBUS-JR10437140" / "interview_prep.md"
    assert out_path.exists()
    captured = capsys.readouterr()
    assert "AIRBUS-JR10437140" in captured.out


def test_aggregate_skill_gaps_handles_empty_applications_dir(tmp_path):
    summary = aggregate_skill_gaps(applications_dir=tmp_path)
    assert summary["analyzed_count"] == 0
    assert summary["top_gaps"] == []
    report_path = write_upskill_report(summary, output_path=tmp_path / "upskill.md")
    assert report_path.exists()
    text = report_path.read_text(encoding="utf-8")
    assert "0" in text


def test_aggregate_skill_gaps_ranks_recurring_gaps(tmp_path):
    for idx, gaps in enumerate([["SysML v2", "Polarion"], ["SysML v2", "Capella"]]):
        d = tmp_path / f"OP-{idx}"
        d.mkdir()
        (d / "analysis.json").write_text(
            json.dumps(
                {
                    "opening_id": f"OP-{idx}",
                    "company": "TestCo",
                    "title": "Lead SE",
                    "skill_gaps": gaps,
                }
            ),
            encoding="utf-8",
        )
    summary = aggregate_skill_gaps(applications_dir=tmp_path)
    assert summary["analyzed_count"] == 2
    assert summary["top_gaps"][0]["skill"] == "SysML v2"
    assert summary["top_gaps"][0]["count"] == 2
    assert summary["top_gaps"][0]["openings"] == ["OP-0", "OP-1"]


def test_aggregate_skill_gaps_and_report_include_missing_standards_and_cli(tmp_path):
    for idx, (gaps, stds) in enumerate(
        [
            (["Polarion", "Polarion"], ["ISO 26262"]),
            (["Polarion", "Capella"], ["ISO 26262", "DO-160"]),
        ]
    ):
        d = tmp_path / f"ROLE-{idx}"
        d.mkdir()
        (d / "analysis.json").write_text(
            json.dumps(
                {
                    "opening_id": f"ROLE-{idx}",
                    "company": f"AeroCo {idx}",
                    "title": "Systems Lead",
                    "skill_gaps": gaps,
                    "missing_standards": stds,
                }
            ),
            encoding="utf-8",
        )

    output_md = tmp_path / "reports" / "upskill_summary.md"
    exit_code = upskill_main(
        [
            "--applications-dir",
            str(tmp_path),
            "--output",
            str(output_md),
        ]
    )
    assert exit_code == 0
    assert output_md.exists()
    report_text = output_md.read_text(encoding="utf-8")
    assert "Polarion" in report_text
    assert "ISO 26262" in report_text
    assert "ROLE-0" in report_text
    assert "ROLE-1" in report_text
