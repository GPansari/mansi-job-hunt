from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from scripts.application_builder import (
    build_application_package,
    build_tailored_resume_data,
    compile_html_to_pdf,
    draft_cover_letter_markdown,
    render_html_from_template,
)
from scripts.profile_loader import load_master_profile


def test_render_html_from_template_escapes_special_characters(tmp_path: Path):
    tpl = tmp_path / "sample.html"
    tpl.write_text("<h1>$TITLE</h1><p>$COMPANY</p>", encoding="utf-8")
    rendered = render_html_from_template(
        tpl,
        {"TITLE": 'Lead Dev & V&V <"Avionics">', "COMPANY": "Collins & RTX"},
    )
    assert "&amp;" in rendered
    assert "&lt;" in rendered
    assert "Collins &amp; RTX" in rendered
    assert '<"Avionics">' not in rendered


def test_compile_html_to_pdf_handles_missing_chrome_gracefully(tmp_path: Path):
    html_file = tmp_path / "doc.html"
    html_file.write_text("<html><body><h1>Hello</h1></body></html>", encoding="utf-8")
    pdf_file = tmp_path / "doc.pdf"
    ok = compile_html_to_pdf(html_file, pdf_file, chrome_bin=tmp_path / "no-chrome")
    assert ok is False
    assert not pdf_file.exists()


def test_tailored_resume_and_cover_letter_grounding():
    profile = load_master_profile()
    opening = {
        "id": "RTX-01889489",
        "company": "Collins Aerospace (RTX)",
        "title": "Principal Engineer - Systems Requirements Architect",
        "location": "Bangalore",
        "skills_matched": ["MBSE", "SysML", "Cameo", "DOORS"],
    }
    analysis = {
        "opening_id": "RTX-01889489",
        "matched_skills": ["MBSE", "SysML", "Cameo", "IBM DOORS"],
        "matched_standards": ["ARP4754A"],
        "skill_gaps": [],
        "priority_keywords": ["MBSE", "SysML", "Cameo", "DOORS", "ARP4754A"],
    }
    resume_data = build_tailored_resume_data(opening, analysis, profile)
    assert resume_data["name"] == "Mansi Agrawal"
    assert resume_data["email"] == profile["candidate"]["email"]
    assert resume_data["phone"] == profile["candidate"]["phone"]
    assert resume_data["core_skills"][0] in {"MBSE", "SysML", "Cameo", "IBM DOORS"}
    assert len(resume_data["experience"]) >= 3
    assert all(
        bullet in profile["dossier_markdown"]
        for role in resume_data["experience"]
        for bullet in role["bullets"]
    )
    letter = draft_cover_letter_markdown(opening, analysis, profile)
    assert "Collins Aerospace (RTX)" in letter
    assert "TBD" not in letter
    assert "[Company]" not in letter


def test_compile_html_to_pdf_invokes_headless_chrome_flags(tmp_path: Path):
    fake_chrome = tmp_path / "chrome"
    fake_chrome.write_text("#!/bin/sh\n", encoding="utf-8")
    html_file = tmp_path / "doc.html"
    html_file.write_text("<html><body><h1>Hello</h1></body></html>", encoding="utf-8")
    pdf_file = tmp_path / "doc.pdf"

    def fake_run(cmd, **kwargs):
        assert cmd[0] == str(fake_chrome)
        assert "--headless=new" in cmd
        assert "--disable-gpu" in cmd
        assert "--no-sandbox" in cmd
        assert f"--print-to-pdf={pdf_file}" in cmd
        assert "--no-pdf-header-footer" in cmd
        assert cmd[-1] == html_file.resolve().as_uri()
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        class Result:
            returncode = 0

        return Result()

    with patch("scripts.application_builder.subprocess.run", side_effect=fake_run):
        ok = compile_html_to_pdf(html_file, pdf_file, chrome_bin=fake_chrome)

    assert ok is True
    assert pdf_file.exists()


def test_build_application_package_writes_escaped_artifacts(tmp_path: Path):
    openings_file = tmp_path / "openings.json"
    openings_file.write_text(
        json.dumps(
            [
                {
                    "id": "TEST-APP-1",
                    "company": "Collins & RTX <India>",
                    "title": 'Lead Systems & V&V Architect ("MBSE")',
                    "location": "Bangalore",
                    "seniority": "Lead",
                    "skills_matched": ["MBSE", "SysML", "Cameo"],
                    "fit_rationale": "Strong MBSE & ARP4754A match.",
                }
            ]
        ),
        encoding="utf-8",
    )
    apps_dir = tmp_path / "applications"
    result = build_application_package(
        opening_id="TEST-APP-1",
        jd_text="Seeking Lead Systems & V&V Architect with MBSE, SysML, Cameo, IBM DOORS, ARP4754A.",
        applications_dir=apps_dir,
        openings_path=openings_file,
        render_pdf=False,
    )

    pkg_dir = apps_dir / "TEST-APP-1"
    assert (pkg_dir / "analysis.json").exists()
    assert (pkg_dir / "analysis.md").exists()
    assert (pkg_dir / "tailored_resume.json").exists()
    assert (pkg_dir / "tailored_resume.html").exists()
    assert (pkg_dir / "cover_letter.md").exists()
    assert (pkg_dir / "cover_letter.html").exists()
    assert result["resume_pdf_generated"] is False
    assert result["cover_letter_pdf_generated"] is False

    resume_html = (pkg_dir / "tailored_resume.html").read_text(encoding="utf-8")
    letter_html = (pkg_dir / "cover_letter.html").read_text(encoding="utf-8")
    assert "Mansi Agrawal" in resume_html
    assert "Collins &amp; RTX &lt;India&gt;" in letter_html
    assert "Lead Systems &amp; V&amp;V Architect (&quot;MBSE&quot;)" in letter_html
    assert "<India>" not in letter_html
    assert "&amp;" in resume_html


def test_bullet_ordering_prioritizes_keyword_overlap_without_alteration():
    profile = load_master_profile()
    opening = {
        "id": "AIRBUS-JR10437140",
        "company": "Airbus India",
        "title": "Systems Engineer",
        "location": "Bangalore",
    }
    analysis = {
        "opening_id": "AIRBUS-JR10437140",
        "matched_skills": ["IBM DOORS", "3DEXPERIENCE", "Digital Thread"],
        "matched_standards": [],
        "priority_keywords": ["3DEXPERIENCE", "DESE", "IBM DOORS", "ReqHub", "DataHub"],
    }
    resume_data = build_tailored_resume_data(opening, analysis, profile)
    boeing_role = resume_data["experience"][0]
    assert boeing_role["company"] == "Boeing India Pvt. Ltd."
    assert "3DEXPERIENCE" in boeing_role["bullets"][0]
    assert "IBM DOORS" in boeing_role["bullets"][0]


def test_resume_fragment_builders_escape_leaf_nodes(tmp_path: Path):
    from scripts.application_builder import (
        DEFAULT_COVER_LETTER_TEMPLATE,
        DEFAULT_RESUME_TEMPLATE,
        main,
    )

    candidate_file = tmp_path / "candidate.json"
    candidate_file.write_text(
        json.dumps(
            {
                "name": "Mansi <Agrawal>",
                "email": "mansi@example.com",
                "phone": "+91-1234567890",
                "linkedin": "https://example.com/in/mansi",
                "location": "Bangalore & Remote",
                "current_title": 'Lead "Systems" Engineer',
                "experience_years": 10,
                "education": 'MS Aerospace <Georgia Tech> & "Honors"',
                "summary": "Built MBSE & V&V <systems>.",
                "core_skills": ["MBSE & SysML", "V&V <HIL>"],
            }
        ),
        encoding="utf-8",
    )
    dossier_file = tmp_path / "dossier.md"
    dossier_file.write_text(
        "# Master\n\n"
        "## Verified Companies\n- Boeing & Co\n\n"
        "## Experience\n"
        "### Lead \"Systems\" Engineer | Boeing & Co, Bangalore | 2020 - Present\n"
        "- Delivered <MBSE> & V&V models for \"777-8F\".\n\n"
        "## Verified Standards\n- ARP4754A\n\n"
        "## Verified Skills & Tools\n- MBSE & SysML\n\n"
        "## Education\n- MS Aerospace <Georgia Tech> & \"Honors\"\n",
        encoding="utf-8",
    )
    openings_file = tmp_path / "openings.json"
    openings_file.write_text(
        json.dumps([{"id": "ESC-1", "company": "Aero & Co", "title": "Lead <SE>", "location": "Bangalore"}]),
        encoding="utf-8",
    )
    apps_dir = tmp_path / "apps"
    exit_code = main(
        [
            "--id",
            "ESC-1",
            "--jd-text",
            "MBSE and ARP4754A",
            "--no-pdf",
            "--openings",
            str(openings_file),
            "--applications-dir",
            str(apps_dir),
            "--candidate",
            str(candidate_file),
            "--dossier",
            str(dossier_file),
        ]
    )
    assert exit_code == 0
    assert DEFAULT_RESUME_TEMPLATE.exists() and DEFAULT_COVER_LETTER_TEMPLATE.exists()
    html_out = (apps_dir / "ESC-1" / "tailored_resume.html").read_text(encoding="utf-8")
    assert "Mansi &lt;Agrawal&gt;" in html_out
    assert "MBSE &amp; SysML" in html_out
    assert "V&amp;V &lt;HIL&gt;" in html_out
    assert "&lt;MBSE&gt; &amp; V&amp;V models for &quot;777-8F&quot;." in html_out
    assert "Boeing &amp; Co" in html_out
    assert "<Agrawal>" not in html_out
    assert "<HIL>" not in html_out
