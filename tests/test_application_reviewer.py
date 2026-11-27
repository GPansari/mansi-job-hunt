from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.application_reviewer import audit_application, main, save_review_report


def _seed_app_dir(
    tmp_path: Path,
    opening_id: str = "TEST-REV",
    resume_skills: list[str] | None = None,
    letter_text: str = "Dear Hiring Team,\nApplying with MBSE and SysML experience.\nRegards,\nMansi Agrawal",
    contact_overrides: dict[str, str] | None = None,
    experience: list[dict[str, object]] | None = None,
    priority_keywords: list[str] | None = None,
) -> Path:
    app_dir = tmp_path / opening_id
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "analysis.json").write_text(
        json.dumps(
            {
                "opening_id": opening_id,
                "priority_keywords": priority_keywords if priority_keywords is not None else ["MBSE", "SysML", "Cameo"],
                "matched_skills": ["MBSE", "SysML"],
                "skill_gaps": [],
            }
        ),
        encoding="utf-8",
    )
    resume_payload: dict[str, object] = {
        "opening_id": opening_id,
        "name": "Mansi Agrawal",
        "email": "agrawal.mansi20@gmail.com",
        "phone": "+91-8779232450",
        "headline": "Lead Systems Engineer",
        "summary": "10 years in MBSE and SysML.",
        "core_skills": resume_skills if resume_skills is not None else ["MBSE", "SysML", "Cameo"],
        "experience": experience
        if experience is not None
        else [{"role": "Lead Systems Engineer", "company": "Boeing India", "bullets": ["Led MBSE adoption"]}],
        "education": ["MS Aerospace Engineering, Georgia Tech"],
    }
    if contact_overrides:
        resume_payload.update(contact_overrides)

    (app_dir / "tailored_resume.json").write_text(json.dumps(resume_payload), encoding="utf-8")
    (app_dir / "cover_letter.md").write_text(letter_text, encoding="utf-8")
    return app_dir


def test_audit_flags_unverified_standard_claim(tmp_path: Path):
    _seed_app_dir(
        tmp_path,
        resume_skills=["MBSE", "SysML", "DO-254", "SysML v2"],
        letter_text="I led SysML v2 certification at Airbus.",
    )
    report = audit_application("TEST-REV", applications_dir=tmp_path)
    assert report["passed"] is False
    assert len(report["unverified_claims"]) >= 1
    assert any("SysML v2" in claim for claim in report["unverified_claims"])


def test_audit_flags_unresolved_placeholders(tmp_path: Path):
    _seed_app_dir(
        tmp_path,
        letter_text="Dear [Hiring Manager], TBD for [Company].",
    )
    report = audit_application("TEST-REV", applications_dir=tmp_path)
    assert report["passed"] is False
    assert any("TBD" in hit or "[" in hit for hit in report["placeholder_hits"])


def test_audit_passes_clean_grounded_application(tmp_path: Path):
    _seed_app_dir(tmp_path)
    report = audit_application("TEST-REV", applications_dir=tmp_path)
    assert report["passed"] is True
    assert report["ats_coverage_pct"] == 100.0
    json_p, md_p = save_review_report(report, applications_dir=tmp_path)
    assert json_p.exists() and md_p.exists()


def test_audit_flags_contact_mismatch_and_unverified_company_and_skill(tmp_path: Path):
    _seed_app_dir(
        tmp_path,
        resume_skills=["MBSE", "Polarion"],
        contact_overrides={"email": "wrong@example.com", "phone": "+1-000-000-0000"},
        experience=[{"role": "Principal SE", "company": "Unverified Aero Corp", "bullets": ["Did MOSA work"]}],
    )
    report = audit_application("TEST-REV", applications_dir=tmp_path)
    assert report["passed"] is False
    assert len(report["contact_mismatch"]) == 2
    assert any("Polarion" in c for c in report["unverified_claims"])
    assert any("Unverified Aero Corp" in c for c in report["unverified_claims"])
    assert any("MOSA" in c for c in report["unverified_claims"])


def test_audit_checks_pdf_page_budget_with_pdfinfo_and_pdftotext_fallback(tmp_path: Path):
    app_dir = _seed_app_dir(tmp_path)
    pdf_path = app_dir / "tailored_resume.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 dummy")

    class FakeProc:
        def __init__(self, returncode: int, stdout: str):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    # 3 pages via pdfinfo -> fails
    with patch("scripts.application_reviewer.subprocess.run", return_value=FakeProc(0, "Title: Resume\nPages: 3\n")):
        report = audit_application("TEST-REV", applications_dir=tmp_path)
    assert report["page_count"] == 3
    assert report["passed"] is False

    # pdfinfo unavailable, fallback to pdftotext form-feed count (2 pages -> passes)
    def fallback_run(cmd, **kwargs):
        if cmd[0] == "pdfinfo":
            raise FileNotFoundError("pdfinfo not found")
        return FakeProc(0, "Page 1 content\n\x0cPage 2 content\n\x0c")

    with patch("scripts.application_reviewer.subprocess.run", side_effect=fallback_run):
        report_ok = audit_application("TEST-REV", applications_dir=tmp_path)
    assert report_ok["page_count"] == 2
    assert report_ok["passed"] is True


def test_audit_partial_ats_coverage_and_cli_exit_codes(tmp_path: Path):
    _seed_app_dir(
        tmp_path,
        priority_keywords=["MBSE", "SysML", "Cameo", "IBM DOORS"],
        resume_skills=["MBSE", "SysML"],
        letter_text="Applying with MBSE experience.",
    )
    report = audit_application("TEST-REV", applications_dir=tmp_path)
    assert report["passed"] is True
    assert report["ats_coverage_pct"] == 50.0
    assert report["ats_keywords_missing"] == ["Cameo", "IBM DOORS"]

    exit_ok = main(["--id", "TEST-REV", "--applications-dir", str(tmp_path)])
    assert exit_ok == 0
    assert (tmp_path / "TEST-REV" / "review.json").exists()
    assert (tmp_path / "TEST-REV" / "review.md").exists()

    # Now introduce a placeholder and verify CLI returns non-zero
    (tmp_path / "TEST-REV" / "cover_letter.md").write_text("Dear {{manager}}, TODO finish.", encoding="utf-8")
    exit_fail = main(["--id", "TEST-REV", "--applications-dir", str(tmp_path)])
    assert exit_fail == 1


def test_audit_rejects_path_traversal_opening_id(tmp_path: Path):
    with pytest.raises(ValueError):
        audit_application("../etc", applications_dir=tmp_path)


def test_audit_passes_package_built_by_application_builder(tmp_path: Path):
    from scripts.application_builder import build_application_package

    openings_file = tmp_path / "openings.json"
    openings_file.write_text(
        json.dumps(
            [
                {
                    "id": "INT-RTX-1",
                    "company": "Collins Aerospace (RTX)",
                    "title": "Lead Systems Engineer - MBSE",
                    "location": "Bangalore",
                    "seniority": "Lead",
                    "skills_matched": ["MBSE", "SysML", "Cameo", "IBM DOORS"],
                }
            ]
        ),
        encoding="utf-8",
    )
    apps_dir = tmp_path / "applications"
    build_application_package(
        opening_id="INT-RTX-1",
        jd_text="Seeking Lead Systems Engineer with MBSE, SysML, Cameo, IBM DOORS, ARP4754A, and Digital Thread.",
        applications_dir=apps_dir,
        openings_path=openings_file,
        render_pdf=False,
    )
    report = audit_application("INT-RTX-1", applications_dir=apps_dir)
    assert report["passed"] is True
    assert report["contact_mismatch"] == []
    assert report["unverified_claims"] == []
    assert report["placeholder_hits"] == []
    assert report["ats_coverage_pct"] >= 80.0


def test_audit_ignores_quoted_target_title_and_company_in_cover_letter(tmp_path: Path):
    target_title = "Lead Software Developer (DESYRE Co-Simulation / SysMLv2)"
    target_company = "Airbus India"
    app_dir = _seed_app_dir(
        tmp_path,
        letter_text=(
            f"Dear Hiring Team at {target_company},\n"
            f"I am excited to apply for the {target_title} opportunity.\n"
            "I bring 10 years of MBSE, SysML, and Cameo experience.\n"
            "Regards,\nMansi Agrawal"
        ),
    )
    resume_path = app_dir / "tailored_resume.json"
    resume_data = json.loads(resume_path.read_text(encoding="utf-8"))
    resume_data["target_title"] = target_title
    resume_data["target_company"] = target_company
    resume_path.write_text(json.dumps(resume_data), encoding="utf-8")

    report = audit_application("TEST-REV", applications_dir=tmp_path)
    assert report["passed"] is True
    assert report["unverified_claims"] == []


def test_audit_fails_when_pdf_exists_but_page_count_unreadable(tmp_path: Path):
    app_dir = _seed_app_dir(tmp_path)
    (app_dir / "tailored_resume.pdf").write_bytes(b"%PDF-1.4 corrupted")

    with patch("scripts.application_reviewer._get_pdf_page_count", return_value=None):
        report = audit_application("TEST-REV", applications_dir=tmp_path)

    assert report["pdf_checked"] is True
    assert report["page_count"] is None
    assert report["passed"] is False
    assert "Could not read page count from tailored_resume.pdf" in report["issues"]


def test_get_pdf_page_count_falls_back_to_pypdf_when_poppler_missing():
    from scripts.application_reviewer import _get_pdf_page_count

    resume_pdf = Path("profile/Mansi_Agrawal_Resume.pdf")
    with patch("scripts.application_reviewer.subprocess.run", side_effect=FileNotFoundError("poppler missing")):
        pages = _get_pdf_page_count(resume_pdf)
    assert isinstance(pages, int) and pages >= 1


