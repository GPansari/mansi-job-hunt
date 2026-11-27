from pathlib import Path
import pytest

from scripts.profile_loader import (
    extract_pdf_text,
    extract_verified_facts,
    load_master_profile,
    parse_dossier_sections,
)


def test_extract_verified_facts_parses_sections_and_candidate():
    dossier = (
        "# Master Dossier\n\n"
        "## Verified Companies\n- Boeing India\n- Collins Aerospace\n\n"
        "## Verified Programs\n- Boeing 777-8F Digital Transformation (DTx)\n\n"
        "## Verified Standards\n- ARP4754A\n- DO-178C\n\n"
        "## Verified Metrics\n- Leads a team of 5 engineers and mentors 4 more\n"
    )
    candidate = {
        "name": "Mansi Agrawal",
        "core_skills": ["MBSE", "SysML", "Cameo"],
        "education": "MS Aerospace Engineering, Georgia Tech",
    }
    facts = extract_verified_facts(dossier, candidate)
    assert "Boeing India" in facts["companies"]
    assert "Boeing 777-8F Digital Transformation (DTx)" in facts["programs"]
    assert "ARP4754A" in facts["standards"]
    assert "MBSE" in facts["skills_and_tools"]
    assert "Leads a team of 5 engineers and mentors 4 more" in facts["metrics"]
    assert "MS Aerospace Engineering, Georgia Tech" in facts["education"]


def test_extract_verified_facts_deduplicates_case_preserving():
    dossier = (
        "## Verified Skills & Tools\n"
        "- MBSE\n"
        "- sysml\n"
        "- ReqHub\n"
    )
    candidate = {
        "core_skills": ["mbse", "SysML", "Cameo"],
        "education": "MS Aerospace Engineering, Georgia Tech",
    }
    facts = extract_verified_facts(dossier, candidate)
    skills = facts["skills_and_tools"]
    assert skills == ["MBSE", "sysml", "ReqHub", "Cameo"]


def test_parse_dossier_sections_splits_h2_headings_only():
    dossier = (
        "# Title\n\n"
        "## Summary\nLead Systems Engineer.\n\n"
        "## Experience\n### Boeing India\n- Built SysML models\n"
    )
    sections = parse_dossier_sections(dossier)
    assert sections["Summary"] == "Lead Systems Engineer."
    assert "### Boeing India" in sections["Experience"]
    assert "- Built SysML models" in sections["Experience"]


def test_load_master_profile_missing_dossier_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_master_profile(
            candidate_path=Path("profile/candidate.json"),
            dossier_path=tmp_path / "missing.md",
        )


def test_load_master_profile_missing_candidate_raises(tmp_path):
    dossier_file = tmp_path / "dossier.md"
    dossier_file.write_text("## Verified Companies\n- Boeing India\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        load_master_profile(
            candidate_path=tmp_path / "missing.json",
            dossier_path=dossier_file,
        )


def test_extract_pdf_text_reads_resume():
    text = extract_pdf_text(Path("profile/Mansi_Agrawal_Resume.pdf"))
    assert "Mansi" in text
    assert len(text.strip()) > 200


def test_load_master_profile_loads_real_files():
    profile = load_master_profile()
    assert profile["candidate"]["name"] == "Mansi Agrawal"
    assert "Summary" in profile["sections"]
    assert "Boeing India Pvt. Ltd." in profile["verified_facts"]["companies"]
    assert "ARP4754A" in profile["verified_facts"]["standards"]
    assert "777-8F" in " ".join(profile["verified_facts"]["programs"])
    assert "MBSE" in profile["verified_facts"]["skills_and_tools"]
    assert "MS Aerospace Engineering, Georgia Tech" in profile["verified_facts"]["education"]
