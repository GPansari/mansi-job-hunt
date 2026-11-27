#!/usr/bin/env python3
"""Fact-Checking Reviewer & ATS Audit Gate.

Audits generated per-role application artifacts (`tailored_resume.json`,
`cover_letter.md`, `analysis.json`, and optional `tailored_resume.pdf`) against
Mansi Agrawal's verified master dossier and canonical candidate profile.
Rejects unverified standards, unverified skills/companies, contact mismatches,
unresolved template placeholders, and resumes exceeding the 2-page PDF budget.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
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
        EXTRA_SKILL_ALIASES,
        KNOWN_AEROSPACE_STANDARDS,
        _dedupe_preserve_case,
        _is_term_verified,
        _matches_any_variant,
    )
    from scripts.profile_loader import (
        DEFAULT_CANDIDATE_PATH,
        DEFAULT_DOSSIER_PATH,
        load_master_profile,
    )
except ModuleNotFoundError:
    from jd_analyzer import (  # type: ignore
        DEFAULT_APPLICATIONS_DIR,
        EXTRA_SKILL_ALIASES,
        KNOWN_AEROSPACE_STANDARDS,
        _dedupe_preserve_case,
        _is_term_verified,
        _matches_any_variant,
    )
    from profile_loader import (  # type: ignore
        DEFAULT_CANDIDATE_PATH,
        DEFAULT_DOSSIER_PATH,
        load_master_profile,
    )

MAX_RESUME_PAGES = 2

_PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:TBD|TODO|FIXME|XXX)\b", re.IGNORECASE),
    re.compile(r"\{\{[^{}]+\}\}"),
    re.compile(
        r"\[(?:[^\[\]]*(?:company|hiring\s+manager|manager|recruiter|role|title|"
        r"position|insert|your\s+|placeholder|tbd|todo|name|date|location)[^\[\]]*)\](?!\()",
        re.IGNORECASE,
    ),
    re.compile(r"\$\{[A-Z0-9_]+\}"),
)
_PDFINFO_PAGES_RE = re.compile(r"^Pages:\s+(\d+)\s*$", re.MULTILINE)


def _validate_opening_id(opening_id: str) -> str:
    """Reject empty or path-traversal opening IDs."""
    cleaned = str(opening_id or "").strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise ValueError(f"Invalid opening_id for review directory: {opening_id!r}")
    return cleaned


def _collect_strings(value: Any) -> list[str]:
    """Recursively collect non-empty strings from nested JSON structures."""
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, list):
        items: list[str] = []
        for elem in value:
            items.extend(_collect_strings(elem))
        return items
    if isinstance(value, dict):
        items = []
        for val in value.values():
            items.extend(_collect_strings(val))
        return items
    return []


def _extract_resume_claim_text(resume_data: dict[str, Any]) -> str:
    """Extract candidate-authored claim fields from `tailored_resume.json`."""
    parts: list[str] = []
    for key in ("headline", "summary", "core_skills", "experience", "education"):
        if key in resume_data:
            parts.extend(_collect_strings(resume_data[key]))
    return "\n".join(parts)


def _skill_variants(skill: str) -> list[str]:
    """Return canonical + alias variants for a skill string."""
    cleaned = skill.strip()
    if not cleaned:
        return []
    variants = [cleaned]
    for key, aliases in EXTRA_SKILL_ALIASES.items():
        if key.casefold() == cleaned.casefold() or any(a.casefold() == cleaned.casefold() for a in aliases):
            variants.extend([key] + list(aliases))
    return _dedupe_preserve_case(variants)


def _check_contact_fidelity(
    resume_data: dict[str, Any],
    candidate: dict[str, Any],
) -> list[str]:
    """Verify name, email, and phone in tailored_resume.json match candidate.json."""
    mismatches: list[str] = []
    for field in ("name", "email", "phone"):
        expected = str(candidate.get(field) or "").strip()
        actual = str(resume_data.get(field) or "").strip()
        if expected and actual != expected:
            mismatches.append(f"{field}: expected '{expected}', got '{actual or '<missing>'}'")
    return mismatches


def _check_unverified_claims(
    resume_data: dict[str, Any],
    cover_letter_text: str,
    verified_facts: dict[str, list[str]],
) -> list[str]:
    """Check aerospace standards, core_skills, and experience[].company against verified_facts."""
    claims: list[str] = []

    verified_standards = [str(s) for s in (verified_facts.get("standards") or []) if str(s).strip()]
    verified_skills = [str(s) for s in (verified_facts.get("skills_and_tools") or []) if str(s).strip()]
    verified_companies = [str(c) for c in (verified_facts.get("companies") or []) if str(c).strip()]
    verified_pool = _dedupe_preserve_case(verified_standards + verified_skills)
    verified_pool_cf = {item.casefold() for item in verified_pool}
    verified_companies_cf = {item.casefold() for item in verified_companies}

    resume_claim_text = _extract_resume_claim_text(resume_data)
    combined_claim_text = f"{resume_claim_text}\n{cover_letter_text}".strip()

    flagged_standards_cf: set[str] = set()
    for std_name, variants in KNOWN_AEROSPACE_STANDARDS.items():
        if _matches_any_variant(combined_claim_text, variants):
            if not _is_term_verified(variants, verified_pool):
                claims.append(f"Unverified standard: {std_name}")
                flagged_standards_cf.add(std_name.casefold())
                flagged_standards_cf.update(v.casefold() for v in variants)

    for raw_skill in resume_data.get("core_skills") or []:
        skill = str(raw_skill).strip()
        if not skill:
            continue
        if skill.casefold() in flagged_standards_cf:
            continue
        if skill.casefold() in verified_pool_cf:
            continue
        variants = _skill_variants(skill)
        if not _is_term_verified(variants, verified_pool):
            claims.append(f"Unverified core skill: {skill}")

    for entry in resume_data.get("experience") or []:
        if not isinstance(entry, dict):
            continue
        company = str(entry.get("company") or "").strip()
        if company and company.casefold() not in verified_companies_cf:
            claims.append(f"Unverified company: {company}")

    return _dedupe_preserve_case(claims)


def _check_placeholders(
    resume_data: dict[str, Any],
    cover_letter_text: str,
) -> list[str]:
    """Detect unresolved placeholder tokens across tailored_resume.json and cover_letter.md."""
    texts = _collect_strings(resume_data) + [cover_letter_text]
    hits: list[str] = []
    for text in texts:
        for pattern in _PLACEHOLDER_PATTERNS:
            for match in pattern.finditer(text):
                hits.append(match.group(0))
    return _dedupe_preserve_case(hits)


def _compute_ats_coverage(
    analysis: dict[str, Any],
    combined_text: str,
) -> tuple[float, list[str], list[str]]:
    """Compute case-insensitive coverage of analysis['priority_keywords']."""
    keywords = _dedupe_preserve_case(
        [str(kw) for kw in (analysis.get("priority_keywords") or []) if str(kw).strip()]
    )
    if not keywords:
        return 100.0, [], []

    matched: list[str] = []
    missing: list[str] = []
    for kw in keywords:
        if _matches_any_variant(combined_text, [kw]):
            matched.append(kw)
        else:
            missing.append(kw)

    pct = round((len(matched) / len(keywords)) * 100.0, 1)
    return pct, matched, missing


def _count_pdf_pages_via_pdftotext(stdout: str) -> int | None:
    """Count PDF pages from `pdftotext` stdout using form-feed (`\\x0c`) delimiters."""
    if not stdout:
        return None
    if stdout.strip():
        stripped = stdout.rstrip("\x0c")
        return len(stripped.split("\x0c"))
    if "\x0c" in stdout:
        return stdout.count("\x0c")
    return None


def _get_pdf_page_count(pdf_path: Path) -> int | None:
    """Determine PDF page count via `pdfinfo`, falling back to `pdftotext` form feeds."""
    if not pdf_path.exists():
        return None

    try:
        info_proc = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if info_proc.returncode == 0 and info_proc.stdout:
            match = _PDFINFO_PAGES_RE.search(info_proc.stdout)
            if match:
                return int(match.group(1))
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        text_proc = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if text_proc.returncode == 0:
            return _count_pdf_pages_via_pdftotext(text_proc.stdout)
    except (OSError, subprocess.SubprocessError):
        pass

    return None


def audit_application(
    opening_id: str,
    applications_dir: Path = DEFAULT_APPLICATIONS_DIR,
    master_profile: dict[str, Any] | None = None,
    candidate_path: Path = DEFAULT_CANDIDATE_PATH,
    dossier_path: Path = DEFAULT_DOSSIER_PATH,
) -> dict[str, Any]:
    """Run fact-checking, placeholder, contact, ATS, and PDF page checks on a package."""
    safe_id = _validate_opening_id(opening_id)
    app_dir = Path(applications_dir) / safe_id

    resume_json_path = app_dir / "tailored_resume.json"
    if not resume_json_path.exists():
        raise FileNotFoundError(f"Required artifact not found: {resume_json_path}")

    if master_profile is None:
        master_profile = load_master_profile(candidate_path=candidate_path, dossier_path=dossier_path)

    candidate = master_profile.get("candidate") or {}
    verified_facts = master_profile.get("verified_facts") or {}

    resume_data = json.loads(resume_json_path.read_text(encoding="utf-8"))

    letter_path = app_dir / "cover_letter.md"
    cover_letter_text = letter_path.read_text(encoding="utf-8") if letter_path.exists() else ""

    analysis_path = app_dir / "analysis.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8")) if analysis_path.exists() else {}

    contact_mismatch = _check_contact_fidelity(resume_data, candidate)
    unverified_claims = _check_unverified_claims(resume_data, cover_letter_text, verified_facts)
    placeholder_hits = _check_placeholders(resume_data, cover_letter_text)

    combined_ats_text = f"{_extract_resume_claim_text(resume_data)}\n{cover_letter_text}".strip()
    ats_coverage_pct, ats_matched, ats_missing = _compute_ats_coverage(analysis, combined_ats_text)

    pdf_path = app_dir / "tailored_resume.pdf"
    page_count = _get_pdf_page_count(pdf_path) if pdf_path.exists() else None

    passed = (
        len(unverified_claims) == 0
        and len(placeholder_hits) == 0
        and len(contact_mismatch) == 0
        and (page_count is None or page_count <= MAX_RESUME_PAGES)
    )

    return {
        "opening_id": safe_id,
        "passed": passed,
        "contact_mismatch": contact_mismatch,
        "unverified_claims": unverified_claims,
        "placeholder_hits": placeholder_hits,
        "ats_coverage_pct": ats_coverage_pct,
        "ats_keywords_matched": ats_matched,
        "ats_keywords_missing": ats_missing,
        "page_count": page_count,
        "max_pages_allowed": MAX_RESUME_PAGES,
        "pdf_checked": pdf_path.exists(),
        "reviewed_at": date.today().isoformat(),
    }


def _format_bullet_list(items: list[str], empty_label: str = "None") -> str:
    """Format a list of strings as markdown bullets."""
    if not items:
        return f"- {empty_label}"
    return "\n".join(f"- {item}" for item in items)


def format_review_markdown(report: dict[str, Any]) -> str:
    """Render an audit report dict as a readable Markdown review summary."""
    status_label = "PASSED" if report.get("passed") else "FAILED"
    page_count = report.get("page_count")
    page_display = (
        f"{page_count} / {report.get('max_pages_allowed', MAX_RESUME_PAGES)} pages"
        if page_count is not None
        else "Not checked (PDF absent)"
    )

    lines = [
        f"# Application Audit Review — `{report.get('opening_id', '')}`",
        "",
        f"- **Gate Status:** **{status_label}**",
        f"- **Reviewed At:** {report.get('reviewed_at', '')}",
        f"- **ATS Keyword Coverage:** {report.get('ats_coverage_pct', 0.0)}%",
        f"- **Resume PDF Page Budget:** {page_display}",
        "",
        "## Contact Mismatches",
        _format_bullet_list(report.get("contact_mismatch", []), empty_label="None (contact details match candidate.json)"),
        "",
        "## Unverified Claims",
        _format_bullet_list(report.get("unverified_claims", []), empty_label="None (all audited claims grounded)"),
        "",
        "## Placeholder Hits",
        _format_bullet_list(report.get("placeholder_hits", []), empty_label="None detected"),
        "",
        "## ATS Keywords Matched",
        _format_bullet_list(report.get("ats_keywords_matched", []), empty_label="None"),
        "",
        "## ATS Keywords Missing",
        _format_bullet_list(report.get("ats_keywords_missing", []), empty_label="None"),
        "",
    ]
    return "\n".join(lines)


def save_review_report(
    report: dict[str, Any],
    applications_dir: Path = DEFAULT_APPLICATIONS_DIR,
) -> tuple[Path, Path]:
    """Persist `review.json` and `review.md` under `applications/<opening_id>/`."""
    safe_id = _validate_opening_id(str(report.get("opening_id") or ""))
    target_dir = Path(applications_dir) / safe_id
    target_dir.mkdir(parents=True, exist_ok=True)

    json_path = target_dir / "review.json"
    md_path = target_dir / "review.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(format_review_markdown(report), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for auditing a tailored application package."""
    parser = argparse.ArgumentParser(description="Fact-check and audit a tailored application package.")
    parser.add_argument("--id", required=True, help="Opening ID under applications/<id>/")
    parser.add_argument("--applications-dir", type=Path, default=DEFAULT_APPLICATIONS_DIR, help="Applications directory")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE_PATH, help="Path to candidate.json")
    parser.add_argument("--dossier", type=Path, default=DEFAULT_DOSSIER_PATH, help="Path to master_dossier.md")

    args = parser.parse_args(argv)
    report = audit_application(
        opening_id=args.id,
        applications_dir=args.applications_dir,
        candidate_path=args.candidate,
        dossier_path=args.dossier,
    )
    json_path, md_path = save_review_report(report, applications_dir=args.applications_dir)

    status_word = "PASSED" if report["passed"] else "FAILED"
    print(f"Audit {status_word} for {report['opening_id']} (ATS coverage: {report['ats_coverage_pct']}%)")
    if report["contact_mismatch"]:
        print(f"Contact mismatches: {', '.join(report['contact_mismatch'])}")
    if report["unverified_claims"]:
        print(f"Unverified claims: {', '.join(report['unverified_claims'])}")
    if report["placeholder_hits"]:
        print(f"Placeholder hits: {', '.join(report['placeholder_hits'])}")
    if report["page_count"] is not None:
        print(f"PDF pages: {report['page_count']}")
    print(f"Saved: {json_path} and {md_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
