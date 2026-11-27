#!/usr/bin/env python3
"""Tailored Resume & Cover Letter Builder and HTML-to-PDF Renderer.

Generates role-specific tailored resumes and cover letters strictly grounded in
Mansi Agrawal's verified master dossier (`profile/master_dossier.md`) and
canonical candidate profile (`profile/candidate.json`), renders print-ready
HTML via `string.Template` with strict `html.escape(..., quote=True)`, and
optionally compiles PDFs via headless Google Chrome.
"""

from __future__ import annotations

import argparse
from datetime import date
import html
import json
from pathlib import Path
import re
from string import Template
import subprocess
import sys
from typing import Any

# Ensure repo root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.jd_analyzer import (
        DEFAULT_APPLICATIONS_DIR,
        DEFAULT_OPENINGS_PATH,
        EXTRA_SKILL_ALIASES,
        analyze_jd,
        load_opening_by_id,
        save_analysis,
    )
    from scripts.profile_loader import (
        DEFAULT_CANDIDATE_PATH,
        DEFAULT_DOSSIER_PATH,
        load_master_profile,
    )
except ModuleNotFoundError:
    from jd_analyzer import (  # type: ignore
        DEFAULT_APPLICATIONS_DIR,
        DEFAULT_OPENINGS_PATH,
        EXTRA_SKILL_ALIASES,
        analyze_jd,
        load_opening_by_id,
        save_analysis,
    )
    from profile_loader import (  # type: ignore
        DEFAULT_CANDIDATE_PATH,
        DEFAULT_DOSSIER_PATH,
        load_master_profile,
    )

DEFAULT_RESUME_TEMPLATE = REPO_ROOT / "templates" / "resume.html"
DEFAULT_COVER_LETTER_TEMPLATE = REPO_ROOT / "templates" / "cover_letter.html"
DEFAULT_CHROME_BIN = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

_H3_PATTERN = re.compile(r"^###(?!#)\s+(.+?)\s*$")
_BULLET_PATTERN = re.compile(r"^[-*]\s+(.+?)\s*$")


def _resolve_template_path(path: Path | str) -> Path:
    """Resolve a template path directly or relative to REPO_ROOT."""
    candidate = Path(path)
    if candidate.exists():
        return candidate
    if not candidate.is_absolute():
        repo_candidate = REPO_ROOT / candidate
        if repo_candidate.exists():
            return repo_candidate
    raise FileNotFoundError(f"Template file not found: {candidate}")


def _validate_opening_id(opening_id: str) -> str:
    """Reject empty or path-traversal opening IDs."""
    cleaned = str(opening_id or "").strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise ValueError(f"Invalid opening_id for output directory: {opening_id!r}")
    return cleaned


def _dedupe_preserve_case(items: list[str]) -> list[str]:
    """Deduplicate strings case-insensitively while preserving first-seen casing."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        item = str(raw).strip()
        if not item:
            continue
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _keyword_variants(term: str) -> list[str]:
    """Return known case/alias variants for a skill or keyword."""
    cleaned = term.strip()
    if not cleaned:
        return []
    variants = [cleaned]
    for key, aliases in EXTRA_SKILL_ALIASES.items():
        if key.casefold() == cleaned.casefold() or any(a.casefold() == cleaned.casefold() for a in aliases):
            variants.extend([key] + list(aliases))
    return _dedupe_preserve_case(variants)


def _text_matches_keyword(text: str, keyword: str) -> bool:
    """Return True if keyword or any known alias appears in text with word boundaries."""
    if not text or not keyword:
        return False
    for variant in _keyword_variants(keyword):
        pattern = r"(?<!\w)" + re.escape(variant) + r"(?!\w)"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _skill_priority_rank(skill: str, priority_keywords: list[str]) -> tuple[int, int]:
    """Rank a candidate skill against priority_keywords (lower is higher priority)."""
    skill_variants = [v.casefold() for v in _keyword_variants(skill)]
    for idx, kw in enumerate(priority_keywords):
        kw_variants = [v.casefold() for v in _keyword_variants(kw)]
        if set(skill_variants) & set(kw_variants):
            return (0, idx)
        if any(sv in kv or kv in sv for sv in skill_variants for kv in kw_variants):
            return (1, idx)
    return (2, len(priority_keywords))


def _split_company_and_location(
    raw_company: str,
    verified_companies: list[str],
) -> tuple[str, str]:
    """Extract canonical company name matching verified_companies and optional location."""
    cleaned = raw_company.strip()
    for vc in sorted(verified_companies, key=len, reverse=True):
        if cleaned.casefold() == vc.casefold():
            return vc, ""
        if cleaned.casefold().startswith(vc.casefold() + ","):
            loc = cleaned[len(vc) + 1 :].strip()
            return vc, loc
    if "," in cleaned:
        comp_part, loc_part = cleaned.rsplit(",", 1)
        return comp_part.strip(), loc_part.strip()
    return cleaned, ""


def _parse_experience_roles(
    experience_section: str,
    verified_companies: list[str],
) -> list[dict[str, Any]]:
    """Parse structured Experience entries (`### Role | Company | Period`) from dossier."""
    roles: list[dict[str, Any]] = []
    current_role: dict[str, Any] | None = None

    for line in experience_section.splitlines():
        h3_match = _H3_PATTERN.match(line)
        if h3_match:
            heading = h3_match.group(1).strip()
            if "|" in heading:
                parts = [p.strip() for p in heading.split("|")]
                role_title = parts[0] if len(parts) > 0 else heading
                raw_company = parts[1] if len(parts) > 1 else ""
                period = parts[2] if len(parts) > 2 else ""
                company, location = _split_company_and_location(raw_company, verified_companies)
                current_role = {
                    "role": role_title,
                    "company": company,
                    "location": location,
                    "period": period,
                    "bullets": [],
                }
                roles.append(current_role)
            else:
                # Subsections like "Earlier Internships" or "Leadership and Volunteering"
                current_role = None
            continue

        if current_role is not None:
            bullet_match = _BULLET_PATTERN.match(line.strip())
            if bullet_match:
                bullet = bullet_match.group(1).strip()
                if bullet:
                    current_role["bullets"].append(bullet)

    return [r for r in roles if r["bullets"]]


def _score_and_order_bullets(bullets: list[str], priority_keywords: list[str]) -> list[str]:
    """Order role bullets by keyword overlap without modifying bullet text."""
    if not priority_keywords:
        return list(bullets)

    scored: list[tuple[int, int, str]] = []
    for idx, bullet in enumerate(bullets):
        hits = sum(1 for kw in priority_keywords if _text_matches_keyword(bullet, kw))
        scored.append((-hits, idx, bullet))

    scored.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored]


def _extract_education_entries(master_profile: dict[str, Any]) -> list[str]:
    """Collect clean, non-redundant verified education entries from dossier."""
    sections = master_profile.get("sections") or {}
    edu_section = sections.get("Education", "")
    lines: list[str] = []
    for line in edu_section.splitlines():
        m = _BULLET_PATTERN.match(line.strip())
        if m:
            entry = m.group(1).strip()
            if entry:
                lines.append(entry)

    # Drop the short summary alias if the full Georgia Tech degree line is present
    has_full_gt = any("Georgia Institute of Technology" in item for item in lines)
    if has_full_gt:
        lines = [item for item in lines if item != "MS Aerospace Engineering, Georgia Tech"]

    if not lines:
        verified_edu = (master_profile.get("verified_facts") or {}).get("education") or []
        lines = [str(item) for item in verified_edu if str(item).strip()]
    return _dedupe_preserve_case(lines)


def build_tailored_resume_data(
    opening: dict[str, Any],
    analysis: dict[str, Any],
    master_profile: dict[str, Any],
) -> dict[str, Any]:
    """Build structured tailored resume data strictly grounded in verified profile facts."""
    candidate = master_profile.get("candidate") or {}
    verified_facts = master_profile.get("verified_facts") or {}
    sections = master_profile.get("sections") or {}

    priority_keywords = _dedupe_preserve_case(
        [str(k) for k in (analysis.get("priority_keywords") or [])]
        + [str(s) for s in (analysis.get("matched_standards") or [])]
        + [str(s) for s in (analysis.get("matched_skills") or [])]
    )

    verified_skills = [str(s) for s in (verified_facts.get("skills_and_tools") or [])]
    verified_standards = [str(s) for s in (verified_facts.get("standards") or [])]
    verified_pool = _dedupe_preserve_case(verified_skills + verified_standards)

    # Prioritize core_skills from candidate.json matching priority_keywords first,
    # then append any matched verified skills/standards and remaining candidate core_skills.
    candidate_core = [str(s) for s in (candidate.get("core_skills") or []) if str(s).strip()]
    extra_matched_verified = [
        item
        for item in (list(analysis.get("matched_standards") or []) + list(analysis.get("matched_skills") or []))
        if any(item.casefold() == vp.casefold() for vp in verified_pool)
        and not any(item.casefold() == cc.casefold() for cc in candidate_core)
    ]
    combined_skills = _dedupe_preserve_case(candidate_core + extra_matched_verified)
    prioritized_skills = sorted(
        enumerate(combined_skills),
        key=lambda pair: (_skill_priority_rank(pair[1], priority_keywords), pair[0]),
    )
    ordered_skills = [skill for _, skill in prioritized_skills]

    # Headline strictly from verified current title + top matched verified capabilities
    current_title = str(candidate.get("current_title") or "Lead Systems Engineer")
    top_tags = [
        skill
        for skill in ordered_skills
        if _skill_priority_rank(skill, priority_keywords)[0] < 2
    ][:4]
    if not top_tags:
        top_tags = ordered_skills[:4]
    headline = f"{current_title} | {' • '.join(top_tags)}" if top_tags else current_title

    # Summary grounded in candidate.json + verified standards/degrees
    base_summary = str(candidate.get("summary") or "").strip()
    verified_matched_stds = [
        std
        for std in (analysis.get("matched_standards") or [])
        if any(std.casefold() == vs.casefold() for vs in verified_standards)
    ]
    summary_parts = [base_summary] if base_summary else []
    if verified_matched_stds:
        summary_parts.append(
            f"Experienced with {', '.join(verified_matched_stds)} compliance and early requirements validation."
        )
    education_tag = str(candidate.get("education") or "").strip()
    if education_tag and education_tag not in " ".join(summary_parts):
        summary_parts.append(f"{education_tag}.")
    summary = " ".join(part for part in summary_parts if part).strip()

    # Parse and score Experience bullets per role without altering factual wording
    verified_companies = [str(c) for c in (verified_facts.get("companies") or [])]
    raw_roles = _parse_experience_roles(sections.get("Experience", ""), verified_companies)
    tailored_experience: list[dict[str, Any]] = []
    for role in raw_roles:
        tailored_experience.append(
            {
                "role": role["role"],
                "company": role["company"],
                "location": role["location"],
                "period": role["period"],
                "bullets": _score_and_order_bullets(role["bullets"], priority_keywords),
            }
        )

    return {
        "opening_id": str(opening.get("id") or analysis.get("opening_id") or ""),
        "target_company": str(opening.get("company") or analysis.get("company") or ""),
        "target_title": str(opening.get("title") or analysis.get("title") or ""),
        "name": str(candidate.get("name") or "Mansi Agrawal"),
        "email": str(candidate.get("email") or ""),
        "phone": str(candidate.get("phone") or ""),
        "linkedin": str(candidate.get("linkedin") or ""),
        "location": str(candidate.get("location") or ""),
        "headline": headline,
        "summary": summary,
        "core_skills": ordered_skills,
        "experience": tailored_experience,
        "education": _extract_education_entries(master_profile),
    }


def draft_cover_letter_markdown(
    opening: dict[str, Any],
    analysis: dict[str, Any],
    master_profile: dict[str, Any],
) -> str:
    """Draft a grounded cover letter in Markdown citing only verified dossier facts."""
    candidate = master_profile.get("candidate") or {}
    verified_facts = master_profile.get("verified_facts") or {}

    name = str(candidate.get("name") or "Mansi Agrawal")
    email = str(candidate.get("email") or "")
    phone = str(candidate.get("phone") or "")
    exp_years = candidate.get("experience_years", 10)
    current_title = str(candidate.get("current_title") or "Lead Systems Engineer")

    company = str(opening.get("company") or analysis.get("company") or "your organization").strip()
    role = str(opening.get("title") or analysis.get("title") or "this Systems Engineering role").strip()
    location = str(opening.get("location") or analysis.get("location") or "").strip()

    verified_skills = [str(s) for s in (verified_facts.get("skills_and_tools") or [])]
    verified_standards = [str(s) for s in (verified_facts.get("standards") or [])]
    verified_pool = verified_skills + verified_standards

    matched_skills = [
        str(s)
        for s in (analysis.get("matched_skills") or [])
        if any(str(s).casefold() == vp.casefold() for vp in verified_pool)
    ]
    matched_standards = [
        str(s)
        for s in (analysis.get("matched_standards") or [])
        if any(str(s).casefold() == vs.casefold() for vs in verified_standards)
    ]

    matched_lower = {s.casefold() for s in matched_skills + matched_standards}
    combined_role_text = f"{role} {' '.join(matched_skills)} {' '.join(matched_standards)}".casefold()

    location_clause = f" in {location}" if location else ""
    intro_para = (
        f"I am writing to express my interest in the {role} opportunity{location_clause} at {company}. "
        f"With {exp_years} years of aerospace systems engineering experience across commercial aircraft "
        f"and UAV programs—and an MS in Aerospace Engineering from Georgia Institute of Technology—I currently "
        f"serve as {current_title} at Boeing India Pvt. Ltd. in Bangalore."
    )

    body_highlights: list[str] = [
        "At Boeing India Pvt. Ltd., I lead the Detailed Modelling and Simulation pilot within Boeing's "
        "Digital Transformation (DTx) initiative, building executable SysML models from system ConOps "
        "in Cameo and MagicDraw for 777-8F electrical and electronic subsystems (including Main AC power, "
        "ELMS, and Backup Electrical Power)."
    ]

    if matched_lower & {"ibm doors", "doors", "3dexperience", "digital thread", "reqhub", "datahub", "dese"}:
        body_highlights.append(
            "In parallel, I maintain end-to-end digital-thread traceability by synchronizing data across "
            "3DEXPERIENCE, DESE, and IBM DOORS through ReqHub and DataHub, enabling early requirements "
            "validation and failure-condition tracing prior to hardware availability."
        )

    if matched_standards:
        stds_text = ", ".join(matched_standards)
        body_highlights.append(
            f"My systems engineering and quality background aligns with rigorous aerospace compliance "
            f"frameworks including {stds_text}, complemented by prior AS9100 quality engineering work "
            f"at Desemco LLC using GD&T, CATIA, and VERICUT."
        )

    if any(kw in combined_role_text for kw in ("uav", "unmanned", "evtol", "defense", "defence", "cfd", "fem", "sizing")):
        body_highlights.append(
            "Previously, as Design and Development Engineer at Omnidyne Systems Pvt. Ltd., I led the "
            "design, sizing, and synthesis of a MALE UAV for an Indian Defence RFI, executing trade "
            "studies across propulsion, materials, and landing gear alongside CFD, FEM, and aeroelastic analysis."
        )

    tech_para = " ".join(body_highlights)

    leadership_para = (
        "Beyond technical architecture, I lead a team of 5 systems engineers and mentor 4 more on MBSE "
        "delivery while managing cross-functional stakeholders across engineering programs. My impact at "
        "Boeing India was recognized with the Engineer of the Quarter award for Systems and Production "
        "Engineering (Q1 2026, selected from 1,000+ engineers) and the Boeing Women in Cloud Corporate "
        "Impact Champion award (July 2026)."
    )

    closing_para = (
        f"I would welcome the opportunity to bring this verified MBSE, requirements architecture, and "
        f"team leadership experience to {company} for the {role} role. Thank you for your time and consideration."
    )

    contact_footer = " | ".join(part for part in (email, phone) if part)
    lines = [
        f"Dear Hiring Team at {company},",
        "",
        intro_para,
        "",
        tech_para,
        "",
        leadership_para,
        "",
        closing_para,
        "",
        "Sincerely,",
        name,
    ]
    if contact_footer:
        lines.append(contact_footer)
    return "\n".join(lines).strip() + "\n"


def render_html_from_template(template_path: Path, context: dict[str, str]) -> str:
    """Render an HTML template via `string.Template`, escaping all plain-text values.

    Keys ending with `_HTML` or `_SAFE_HTML` are treated as pre-escaped HTML
    fragments (where every leaf text node has already been escaped with
    `html.escape(..., quote=True)`). All other context values are escaped here.
    """
    resolved = _resolve_template_path(template_path)
    raw_template = resolved.read_text(encoding="utf-8")

    safe_context: dict[str, str] = {}
    for key, value in context.items():
        text_val = "" if value is None else str(value)
        if key.endswith("_HTML") or key.endswith("_SAFE_HTML"):
            safe_context[key] = text_val
        else:
            safe_context[key] = html.escape(text_val, quote=True)

    return Template(raw_template).substitute(safe_context)


def _build_skills_html(skills: list[str]) -> str:
    """Build pre-escaped HTML list for resume skills."""
    items = [
        f'<li class="skill-item">{html.escape(str(skill), quote=True)}</li>'
        for skill in skills
        if str(skill).strip()
    ]
    return '<ul class="skills-list">\n        ' + "\n        ".join(items) + "\n      </ul>"


def _build_experience_html(experience: list[dict[str, Any]]) -> str:
    """Build pre-escaped HTML blocks for resume experience entries."""
    blocks: list[str] = []
    for entry in experience:
        role = html.escape(str(entry.get("role") or ""), quote=True)
        company = html.escape(str(entry.get("company") or ""), quote=True)
        location = str(entry.get("location") or "").strip()
        company_display = f"{company}, {html.escape(location, quote=True)}" if location else company
        period = html.escape(str(entry.get("period") or ""), quote=True)
        bullets_html = "\n          ".join(
            f"<li>{html.escape(str(b), quote=True)}</li>"
            for b in (entry.get("bullets") or [])
            if str(b).strip()
        )
        blocks.append(
            f"""<article class="role-entry">
        <div class="role-header">
          <h3 class="role-title">{role} <span class="role-company">&mdash; {company_display}</span></h3>
          <span class="role-period">{period}</span>
        </div>
        <ul class="role-bullets">
          {bullets_html}
        </ul>
      </article>"""
        )
    return "\n      ".join(blocks)


def _build_education_html(education: list[str]) -> str:
    """Build pre-escaped HTML list for resume education entries."""
    items = [
        f"<li>{html.escape(str(item), quote=True)}</li>"
        for item in education
        if str(item).strip()
    ]
    return '<ul class="education-list">\n        ' + "\n        ".join(items) + "\n      </ul>"


def _markdown_letter_to_body_html(letter_markdown: str) -> str:
    """Convert plain-text/markdown cover letter paragraphs into escaped HTML `<p>` tags."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", letter_markdown.strip()) if p.strip()]
    html_paragraphs: list[str] = []
    for para in paragraphs:
        lines = [html.escape(line.strip(), quote=True) for line in para.splitlines() if line.strip()]
        html_paragraphs.append(f"<p>{'<br>'.join(lines)}</p>")
    return "\n      ".join(html_paragraphs)


def compile_html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    chrome_bin: Path = DEFAULT_CHROME_BIN,
) -> bool:
    """Compile a local HTML file to PDF via headless Google Chrome."""
    chrome = Path(chrome_bin)
    source_html = Path(html_path)
    target_pdf = Path(pdf_path)

    if not chrome.exists() or not source_html.exists():
        return False

    target_pdf.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(chrome),
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--print-to-pdf={target_pdf}",
        "--no-pdf-header-footer",
        source_html.resolve().as_uri(),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return result.returncode == 0 and target_pdf.exists() and target_pdf.stat().st_size > 0


def build_application_package(
    opening_id: str,
    jd_text: str | None = None,
    applications_dir: Path = DEFAULT_APPLICATIONS_DIR,
    render_pdf: bool = True,
    openings_path: Path = DEFAULT_OPENINGS_PATH,
    candidate_path: Path = DEFAULT_CANDIDATE_PATH,
    dossier_path: Path = DEFAULT_DOSSIER_PATH,
    resume_template_path: Path = DEFAULT_RESUME_TEMPLATE,
    cover_letter_template_path: Path = DEFAULT_COVER_LETTER_TEMPLATE,
    chrome_bin: Path = DEFAULT_CHROME_BIN,
) -> dict[str, Any]:
    """Assemble full per-role tailored application package under `applications/<opening_id>/`."""
    safe_id = _validate_opening_id(opening_id)
    opening = load_opening_by_id(safe_id, openings_path=openings_path)
    master_profile = load_master_profile(candidate_path=candidate_path, dossier_path=dossier_path)

    pkg_dir = Path(applications_dir) / safe_id
    pkg_dir.mkdir(parents=True, exist_ok=True)
    analysis_json_path = pkg_dir / "analysis.json"
    analysis_md_path = pkg_dir / "analysis.md"

    if jd_text is not None:
        analysis = analyze_jd(opening, jd_text, master_profile)
        analysis_json_path, analysis_md_path = save_analysis(analysis, applications_dir=applications_dir)
    elif analysis_json_path.exists():
        analysis = json.loads(analysis_json_path.read_text(encoding="utf-8"))
    else:
        fallback_jd_parts = [
            str(opening.get("title") or ""),
            str(opening.get("team") or ""),
            str(opening.get("fit_rationale") or ""),
            " ".join(str(s) for s in opening.get("skills_matched", [])),
        ]
        fallback_jd = "\n".join(part for part in fallback_jd_parts if part.strip())
        analysis = analyze_jd(opening, fallback_jd, master_profile)
        analysis_json_path, analysis_md_path = save_analysis(analysis, applications_dir=applications_dir)

    resume_data = build_tailored_resume_data(opening, analysis, master_profile)
    resume_json_path = pkg_dir / "tailored_resume.json"
    resume_json_path.write_text(
        json.dumps(resume_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    contact_parts = [
        resume_data.get("location", ""),
        resume_data.get("email", ""),
        resume_data.get("phone", ""),
        resume_data.get("linkedin", ""),
    ]
    contact_line = " | ".join(part for part in contact_parts if str(part).strip())

    resume_html = render_html_from_template(
        resume_template_path,
        {
            "NAME": resume_data["name"],
            "HEADLINE": resume_data["headline"],
            "CONTACT_LINE": contact_line,
            "SUMMARY": resume_data["summary"],
            "SKILLS_HTML": _build_skills_html(resume_data["core_skills"]),
            "EXPERIENCE_HTML": _build_experience_html(resume_data["experience"]),
            "EDUCATION_HTML": _build_education_html(resume_data["education"]),
        },
    )
    resume_html_path = pkg_dir / "tailored_resume.html"
    resume_html_path.write_text(resume_html, encoding="utf-8")

    cover_letter_md = draft_cover_letter_markdown(opening, analysis, master_profile)
    cover_letter_md_path = pkg_dir / "cover_letter.md"
    cover_letter_md_path.write_text(cover_letter_md, encoding="utf-8")

    cover_letter_html = render_html_from_template(
        cover_letter_template_path,
        {
            "NAME": resume_data["name"],
            "CONTACT_LINE": contact_line,
            "DATE": date.today().strftime("%B %d, %Y"),
            "COMPANY": str(opening.get("company") or analysis.get("company") or ""),
            "ROLE": str(opening.get("title") or analysis.get("title") or ""),
            "BODY_HTML": _markdown_letter_to_body_html(cover_letter_md),
        },
    )
    cover_letter_html_path = pkg_dir / "cover_letter.html"
    cover_letter_html_path.write_text(cover_letter_html, encoding="utf-8")

    resume_pdf_path = pkg_dir / "tailored_resume.pdf"
    cover_letter_pdf_path = pkg_dir / "cover_letter.pdf"
    resume_pdf_ok = False
    letter_pdf_ok = False
    if render_pdf:
        resume_pdf_ok = compile_html_to_pdf(resume_html_path, resume_pdf_path, chrome_bin=chrome_bin)
        letter_pdf_ok = compile_html_to_pdf(cover_letter_html_path, cover_letter_pdf_path, chrome_bin=chrome_bin)

    return {
        "opening_id": safe_id,
        "package_dir": pkg_dir,
        "analysis_json": analysis_json_path,
        "analysis_md": analysis_md_path,
        "tailored_resume_json": resume_json_path,
        "tailored_resume_html": resume_html_path,
        "tailored_resume_pdf": resume_pdf_path if resume_pdf_ok else None,
        "cover_letter_md": cover_letter_md_path,
        "cover_letter_html": cover_letter_html_path,
        "cover_letter_pdf": cover_letter_pdf_path if letter_pdf_ok else None,
        "resume_pdf_generated": resume_pdf_ok,
        "cover_letter_pdf_generated": letter_pdf_ok,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for building tailored resume and cover-letter application packages."""
    parser = argparse.ArgumentParser(description="Build tailored resume, cover letter, and PDFs.")
    parser.add_argument("--id", required=True, help="Opening ID from data/openings.json")
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--jd-file", type=Path, help="Path to local text/markdown JD file")
    source_group.add_argument("--jd-text", type=str, help="Raw job description text")
    parser.add_argument("--no-pdf", action="store_true", help="Skip headless Chrome PDF compilation")
    parser.add_argument("--openings", type=Path, default=DEFAULT_OPENINGS_PATH, help="Path to openings.json")
    parser.add_argument("--applications-dir", type=Path, default=DEFAULT_APPLICATIONS_DIR, help="Output directory")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE_PATH, help="Path to candidate.json")
    parser.add_argument("--dossier", type=Path, default=DEFAULT_DOSSIER_PATH, help="Path to master_dossier.md")
    parser.add_argument("--chrome-bin", type=Path, default=DEFAULT_CHROME_BIN, help="Path to Google Chrome binary")

    args = parser.parse_args(argv)

    jd_text: str | None = None
    if args.jd_file is not None:
        jd_text = args.jd_file.read_text(encoding="utf-8")
    elif args.jd_text is not None:
        jd_text = args.jd_text

    result = build_application_package(
        opening_id=args.id,
        jd_text=jd_text,
        applications_dir=args.applications_dir,
        render_pdf=not args.no_pdf,
        openings_path=args.openings,
        candidate_path=args.candidate,
        dossier_path=args.dossier,
        chrome_bin=args.chrome_bin,
    )

    print(f"Built application package for {result['opening_id']} in {result['package_dir']}")
    print(f"Resume HTML: {result['tailored_resume_html']}")
    print(f"Cover Letter HTML: {result['cover_letter_html']}")
    print(f"Resume PDF generated: {result['resume_pdf_generated']}")
    print(f"Cover Letter PDF generated: {result['cover_letter_pdf_generated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
