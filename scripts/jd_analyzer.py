#!/usr/bin/env python3
"""Deep Job Description Fetcher & Qualitative Alignment Analyzer.

Fetches job descriptions from non-LinkedIn public ATS URLs (or reads local
text/files), evaluates qualitative alignment against Mansi Agrawal's verified
master dossier and candidate profile, detects tool/standard gaps, and persists
structured `analysis.json` and `analysis.md` artifacts per opening.
"""

from __future__ import annotations

import argparse
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlparse

import requests

# Ensure repo root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.profile_loader import load_master_profile
    from scripts.scorer import SKILL_ALIASES, load_candidate_profile
except ModuleNotFoundError:
    from profile_loader import load_master_profile  # type: ignore
    from scorer import SKILL_ALIASES, load_candidate_profile  # type: ignore

DEFAULT_OPENINGS_PATH = Path("data/openings.json")
DEFAULT_APPLICATIONS_DIR = Path("applications")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

KNOWN_AEROSPACE_STANDARDS: dict[str, list[str]] = {
    "ARP4754A": SKILL_ALIASES.get("ARP4754A", ["ARP4754A", "ARP4754", "ARP 4754A", "ARP 4754", "ED-79A"]),
    "ARP4761": SKILL_ALIASES.get("ARP4761", ["ARP4761", "ARP 4761"]),
    "DO-178C": SKILL_ALIASES.get("DO-178C", ["DO-178C", "DO 178C", "DO178C", "DO-178"]),
    "DO-254": SKILL_ALIASES.get("DO-254", ["DO-254", "DO 254", "DO254"]),
    "DO-160": ["DO-160", "DO-160G", "DO 160", "RTCA DO-160"],
    "AS9100": ["AS9100", "AS 9100", "AS9100D"],
    "ISO 26262": ["ISO 26262", "ISO26262"],
    "SysML v2": ["SysML v2", "SysMLv2", "SysML 2.0"],
    "MOSA": ["MOSA", "Modular Open Systems Approach"],
    "ARINC 429": ["ARINC 429", "ARINC-429", "ARINC429"],
    "AFDX": ["AFDX", "ARINC 664"],
    "MIL-STD-882E": ["MIL-STD-882E", "MIL-STD-882", "MIL STD 882E"],
}

CURATED_GAP_TERMS: dict[str, list[str]] = {
    "Polarion": ["Polarion", "Teamcenter Polarion", "Polarion ALM"],
    "Teamcenter": ["Teamcenter", "Siemens Teamcenter"],
    "Rhapsody": ["Rhapsody", "IBM Rhapsody", "Rational Rhapsody"],
    "Capella": ["Capella", "Eclipse Capella", "Arcadia"],
    "Enterprise Architect": ["Enterprise Architect", "Sparx Enterprise Architect"],
    "SysML v2": ["SysML v2", "SysMLv2", "SysML 2.0"],
    "Simulink": ["Simulink", "MATLAB/Simulink"],
    "LabVIEW": ["LabVIEW"],
    "Jama": ["Jama", "Jama Connect", "Jama Software"],
    "Windchill": ["Windchill", "PTC Windchill"],
    "SCADE": ["SCADE", "Ansys SCADE", "SCADE Suite"],
}

EXTRA_SKILL_ALIASES: dict[str, list[str]] = {
    **SKILL_ALIASES,
    "MBSE": ["MBSE", "Model-Based Systems Engineering", "Model Based Systems Engineering"],
    "SysML": ["SysML"],
    "ConOps": ["ConOps", "Concept of Operations", "ConOps-driven modelling"],
    "MATLAB": ["MATLAB", "MATLAB/Simulink"],
    "Simulink": ["Simulink", "MATLAB/Simulink"],
    "CATIA V5": ["CATIA V5", "CATIA"],
    "SOLIDWORKS": ["SOLIDWORKS", "SolidWorks"],
    "C/C++": ["C/C++", "C++"],
    "CFD": ["CFD", "Computational Fluid Dynamics"],
    "FEM": ["FEM", "Finite Element", "FEA"],
    "Aeroelastic analysis": ["Aeroelastic analysis", "Aeroelastic", "Aeroelasticity"],
}

DOMAIN_KEYWORDS: list[str] = [
    "Systems Engineering",
    "Systems Architecture",
    "Requirements Management",
    "Requirements",
    "Avionics",
    "Electrical Systems",
    "Flight Control",
    "Safety Assessment",
    "Verification & Validation",
    "Simulation",
    "eVTOL",
    "UAV",
    "Commercial Aircraft",
    "Defense Aerospace",
    "Spacetech",
    "Digital Thread",
    "MBSE",
    "SysML",
]


class _HTMLTextExtractor(HTMLParser):
    """Lightweight stdlib HTML-to-text extractor skipping script/style blocks."""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}
    _BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl",
        "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2",
        "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol",
        "p", "pre", "section", "table", "td", "th", "tr", "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        if tag_l in self._SKIP_TAGS:
            self._skip_depth += 1
        elif self._skip_depth == 0 and tag_l in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l in self._SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
        elif self._skip_depth == 0 and tag_l in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data:
            self._chunks.append(data)

    def get_text(self) -> str:
        raw = "".join(self._chunks)
        lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in raw.splitlines()]
        cleaned = "\n".join(line for line in lines if line)
        return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _resolve_existing_path(path: Path | str) -> Path:
    """Resolve an existing file path directly or relative to REPO_ROOT."""
    candidate = Path(path)
    if candidate.exists():
        return candidate
    if not candidate.is_absolute():
        repo_candidate = REPO_ROOT / candidate
        if repo_candidate.exists():
            return repo_candidate
    raise FileNotFoundError(f"Required file not found: {candidate}")


def _html_to_text(html_content: str) -> str:
    """Strip scripts, styles, and tags from HTML and normalize whitespace."""
    extractor = _HTMLTextExtractor()
    extractor.feed(html_content)
    extractor.close()
    return extractor.get_text()


def _extract_json_text_segments(payload: Any) -> list[str]:
    """Recursively collect meaningful string segments from JSON ATS payloads."""
    segments: list[str] = []
    if isinstance(payload, dict):
        preferred_keys = (
            "title",
            "name",
            "jobDescription",
            "description",
            "descriptionPlain",
            "content",
            "text",
            "summary",
            "responsibilities",
            "qualifications",
            "requirements",
        )
        seen_keys: set[str] = set()
        for key in preferred_keys:
            if key in payload:
                seen_keys.add(key)
                segments.extend(_extract_json_text_segments(payload[key]))
        for key, value in payload.items():
            if key not in seen_keys and isinstance(value, (dict, list)):
                segments.extend(_extract_json_text_segments(value))
    elif isinstance(payload, list):
        for item in payload:
            segments.extend(_extract_json_text_segments(item))
    elif isinstance(payload, str):
        cleaned = payload.strip()
        if cleaned:
            if "<" in cleaned and ">" in cleaned:
                cleaned = _html_to_text(cleaned)
            if cleaned:
                segments.append(cleaned)
    return segments


def _dedupe_preserve_case(items: list[str]) -> list[str]:
    """Deduplicate strings case-insensitively while preserving first-seen casing."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        item = raw.strip()
        if not item:
            continue
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _matches_any_variant(text: str, variants: list[str]) -> bool:
    """Return True if any variant appears in text with word-like boundaries."""
    if not text:
        return False
    for variant in variants:
        cleaned = variant.strip()
        if not cleaned:
            continue
        pattern = r"(?<!\w)" + re.escape(cleaned) + r"(?!\w)"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _is_term_verified(variants: list[str], verified_items: list[str]) -> bool:
    """Return True if any variant matches an entry in verified_items."""
    for item in verified_items:
        if _matches_any_variant(item, variants):
            return True
    return False


def load_opening_by_id(
    opening_id: str,
    openings_path: Path = DEFAULT_OPENINGS_PATH,
) -> dict[str, Any]:
    """Load an opening record by exact ID from `data/openings.json`."""
    resolved = _resolve_existing_path(openings_path)
    openings = json.loads(resolved.read_text(encoding="utf-8"))
    for opening in openings:
        if opening.get("id") == opening_id:
            return opening
    raise KeyError(f"Opening ID not found: {opening_id}")


def fetch_jd_text(url: str, timeout: int = 15) -> str:
    """Fetch and clean job description text from a non-LinkedIn public ATS URL.

    Raises:
        ValueError: If the URL is invalid or points to a `linkedin.com` host.
    """
    cleaned_url = (url or "").strip()
    parsed = urlparse(cleaned_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid job posting URL: {url!r}")

    hostname = (parsed.hostname or "").lower()
    if hostname == "linkedin.com" or hostname.endswith(".linkedin.com"):
        raise ValueError(
            "LinkedIn URLs must not be auto-scraped; pass --jd-file or --jd-text instead."
        )

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    response = requests.get(cleaned_url, headers=headers, timeout=timeout)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "").lower()
    body = response.text or ""
    if "application/json" in content_type or body.lstrip().startswith("{"):
        try:
            payload = response.json() if hasattr(response, "json") else json.loads(body)
        except ValueError:
            payload = None
        if payload is not None:
            segments = _extract_json_text_segments(payload)
            if segments:
                return "\n\n".join(_dedupe_preserve_case(segments))

    return _html_to_text(body)


def _assess_seniority_alignment(
    opening: dict[str, Any],
    jd_text: str,
    candidate: dict[str, Any],
) -> str:
    """Evaluate alignment between the role seniority and candidate's 10+ years Lead background."""
    title = str(opening.get("title") or "")
    seniority = str(opening.get("seniority") or "")
    combined = f"{title} {seniority} {jd_text}".lower()
    exp_years = candidate.get("experience_years", 10)

    if any(kw in combined for kw in ("intern", "fresher", "apprentice", "graduate trainee", "entry level")):
        return "Mismatch — Entry/junior scope below candidate's 10+ years Lead Systems Engineer level"

    years_matches = [int(y) for y in re.findall(r"(\d{1,2})\s*\+?\s*(?:years|yrs)", combined)]
    max_req_years = max(years_matches) if years_matches else None

    if any(kw in f"{title} {seniority}".lower() for kw in ("director", "vp", "vice president")):
        return f"Stretch — Executive scope; emphasize team leadership (5 direct, 4 mentored) and {exp_years} yrs"

    if max_req_years and max_req_years >= 15:
        return f"Stretch — Requests {max_req_years}+ yrs experience vs {exp_years} yrs; lean on DTx & leadership scope"

    if any(
        kw in f"{title} {seniority}".lower()
        for kw in ("lead", "principal", "staff", "architect", "manager", "senior")
    ):
        return (
            f"Strong — Role level ({seniority or title}) aligns with {exp_years} yrs aerospace SE "
            "and team leadership (5 direct, 4 mentored)"
        )

    return f"Moderate — Verify exact level expectations against {exp_years} yrs Lead Systems Engineer experience"


def _assess_location_alignment(
    opening: dict[str, Any],
    jd_text: str,
    candidate: dict[str, Any],
) -> str:
    """Evaluate alignment against Bangalore/Bengaluru target location."""
    target_locations = [str(loc).lower() for loc in candidate.get("target_locations", ["Bangalore", "Bengaluru"])]
    opening_loc = str(opening.get("location") or "").strip()
    loc_lower = opening_loc.lower()

    if any(t in loc_lower for t in target_locations) or "bangalore" in loc_lower or "bengaluru" in loc_lower:
        return f"Bangalore match ({opening_loc})"
    if not opening_loc:
        jd_lower = jd_text.lower()
        if "bangalore" in jd_lower or "bengaluru" in jd_lower:
            return "Bangalore match (mentioned in JD)"
        if "remote" in jd_lower or "hybrid" in jd_lower:
            return "Partial — Remote/Hybrid mentioned; confirm Bangalore eligibility"
        return "Unspecified — Confirm Bangalore/Bengaluru location"
    if "remote" in loc_lower or "hybrid" in loc_lower:
        return f"Partial — Remote/Hybrid ({opening_loc})"
    return f"Mismatch — Outside Bangalore ({opening_loc})"


def _build_recommended_angles(
    opening: dict[str, Any],
    jd_text: str,
    matched_skills: list[str],
    matched_standards: list[str],
    skill_gaps: list[str],
    missing_standards: list[str],
    verified_facts: dict[str, list[str]],
) -> list[str]:
    """Generate positioning angles strictly grounded in verified dossier facts."""
    angles: list[str] = []
    combined_lower = f"{opening.get('title', '')} {jd_text}".lower()
    matched_skill_lower = {s.lower() for s in matched_skills}
    matched_std_lower = {s.lower() for s in matched_standards}

    if matched_skill_lower & {"mbse", "sysml", "cameo", "magicdraw", "conops"}:
        angles.append(
            "Highlight Boeing 777-8F Digital Transformation (DTx) MBSE leadership: "
            "building executable SysML models from ConOps for EE subsystems (Main AC, ELMS, Backup Power)."
        )

    if matched_skill_lower & {"ibm doors", "doors", "3dexperience", "digital thread", "reqhub", "datahub", "dese"}:
        angles.append(
            "Emphasize end-to-end digital-thread traceability across 3DEXPERIENCE, DESE, "
            "and IBM DOORS via ReqHub and DataHub."
        )

    if (
        matched_skill_lower & {"v&v", "verification and validation planning"}
        or matched_std_lower & {"arp4754a", "arp4761", "do-178c", "do-254", "as9100"}
    ):
        stds = ", ".join(matched_standards) if matched_standards else "ARP4754A/DO-178C"
        angles.append(
            f"Showcase early requirements validation, failure-condition tracing, and compliance alignment ({stds})."
        )

    if any(kw in combined_lower for kw in ("uav", "unmanned", "evtol", "defense", "defence", "trade study", "sizing")):
        angles.append(
            "Connect Omnidyne Systems MALE UAV design, sizing, and synthesis (Indian Defence RFI) "
            "plus CFD/FEM/aeroelastic trade studies to rapid architecture trade-offs."
        )

    if any(kw in combined_lower for kw in ("lead", "manager", "mentor", "principal", "staff", "team")):
        angles.append(
            "Lead with people & technical leadership: managing 5 engineers and mentoring 4 at Boeing India, "
            "Engineer of the Quarter (Q1 2026), and Boeing Women in Cloud Corporate Impact Champion (July 2026)."
        )

    if skill_gaps or missing_standards:
        gaps_combined = ", ".join(skill_gaps + missing_standards)
        angles.append(
            f"Address gaps transparently ({gaps_combined}) by framing transferable mastery in "
            "Cameo/MagicDraw, 3DEXPERIENCE, and IBM DOORS rather than claiming unverified tool fluency."
        )

    if not angles and verified_facts.get("programs"):
        angles.append(
            "Anchor positioning on 10 years of commercial aircraft and UAV systems engineering, "
            "combining Boeing 777-8F DTx MBSE execution with MS Aerospace Engineering (Georgia Tech)."
        )

    return _dedupe_preserve_case(angles)


def analyze_jd(
    opening: dict[str, Any],
    jd_text: str,
    master_profile: dict[str, Any],
) -> dict[str, Any]:
    """Analyze qualitative alignment between a JD, an opening, and Mansi's verified profile."""
    candidate = master_profile.get("candidate") or load_candidate_profile()
    verified_facts = master_profile.get("verified_facts") or {}

    verified_skills = list(verified_facts.get("skills_and_tools") or [])
    for cs in candidate.get("core_skills", []):
        if cs not in verified_skills:
            verified_skills.append(cs)
    verified_standards = list(verified_facts.get("standards") or [])
    verified_combined = _dedupe_preserve_case(verified_skills + verified_standards)

    search_text = f"{opening.get('title', '')}\n{jd_text or ''}".strip()

    # 1. Standards matching & missing standards
    matched_standards: list[str] = []
    missing_standards: list[str] = []
    for std_name, variants in KNOWN_AEROSPACE_STANDARDS.items():
        if _matches_any_variant(search_text, variants):
            if _is_term_verified(variants, verified_combined):
                matched_standards.append(std_name)
            else:
                missing_standards.append(std_name)

    for v_std in verified_standards:
        if v_std not in matched_standards and _matches_any_variant(search_text, [v_std]):
            matched_standards.append(v_std)

    matched_standards_cf = {s.casefold() for s in matched_standards}

    # 2. Candidate verified skills matching
    matched_skills: list[str] = []
    for skill in verified_skills:
        if skill.casefold() in matched_standards_cf:
            continue
        variants = EXTRA_SKILL_ALIASES.get(skill, [skill])
        if skill not in variants:
            variants = [skill] + variants
        if _matches_any_variant(search_text, variants):
            matched_skills.append(skill)

    # Also check canonical SKILL_ALIASES keys that aren't standards if verified
    for alias_key, variants in EXTRA_SKILL_ALIASES.items():
        if alias_key.casefold() in matched_standards_cf:
            continue
        if _matches_any_variant(search_text, variants) and _is_term_verified([alias_key] + variants, verified_skills):
            matched_skills.append(alias_key)

    matched_skills = _dedupe_preserve_case(matched_skills)
    matched_standards = _dedupe_preserve_case(matched_standards)
    missing_standards = _dedupe_preserve_case(missing_standards)

    # 3. Curated gap detection against verified skills + standards
    skill_gaps: list[str] = []
    for gap_term, variants in CURATED_GAP_TERMS.items():
        if _matches_any_variant(jd_text or "", variants):
            if not _is_term_verified(variants, verified_combined):
                skill_gaps.append(gap_term)
    skill_gaps = _dedupe_preserve_case(skill_gaps)

    # 4. Seniority & location alignment
    seniority_alignment = _assess_seniority_alignment(opening, jd_text or "", candidate)
    location_alignment = _assess_location_alignment(opening, jd_text or "", candidate)

    # 5. Priority keywords & grounded positioning angles
    domain_hits = [kw for kw in DOMAIN_KEYWORDS if _matches_any_variant(search_text, [kw])]
    priority_keywords = _dedupe_preserve_case(matched_standards + matched_skills + domain_hits)[:15]

    recommended_angles = _build_recommended_angles(
        opening=opening,
        jd_text=jd_text or "",
        matched_skills=matched_skills,
        matched_standards=matched_standards,
        skill_gaps=skill_gaps,
        missing_standards=missing_standards,
        verified_facts=verified_facts,
    )

    return {
        "opening_id": opening.get("id", ""),
        "company": opening.get("company", ""),
        "title": opening.get("title", ""),
        "location": opening.get("location", ""),
        "matched_skills": matched_skills,
        "skill_gaps": skill_gaps,
        "matched_standards": matched_standards,
        "missing_standards": missing_standards,
        "seniority_alignment": seniority_alignment,
        "location_alignment": location_alignment,
        "priority_keywords": priority_keywords,
        "recommended_angles": recommended_angles,
        "analyzed_at": date.today().isoformat(),
    }


def _format_bullet_list(items: list[str], empty_label: str = "None identified") -> str:
    """Format a list of strings as markdown bullets."""
    if not items:
        return f"- {empty_label}"
    return "\n".join(f"- {item}" for item in items)


def format_analysis_markdown(analysis: dict[str, Any]) -> str:
    """Render an analysis dictionary into a readable Markdown report."""
    title = analysis.get("title", "Unknown Role")
    company = analysis.get("company", "Unknown Company")
    lines = [
        f"# JD Alignment Analysis — {title} ({company})",
        "",
        f"- **Opening ID:** `{analysis.get('opening_id', '')}`",
        f"- **Analyzed At:** {analysis.get('analyzed_at', '')}",
        f"- **Seniority Alignment:** {analysis.get('seniority_alignment', '')}",
        f"- **Location Alignment:** {analysis.get('location_alignment', '')}",
        "",
        "## Matched Skills",
        _format_bullet_list(analysis.get("matched_skills", [])),
        "",
        "## Matched Standards",
        _format_bullet_list(analysis.get("matched_standards", [])),
        "",
        "## Skill Gaps",
        _format_bullet_list(analysis.get("skill_gaps", []), empty_label="None detected"),
        "",
        "## Missing Standards",
        _format_bullet_list(analysis.get("missing_standards", []), empty_label="None detected"),
        "",
        "## Priority Keywords",
        _format_bullet_list(analysis.get("priority_keywords", [])),
        "",
        "## Recommended Positioning Angles",
        _format_bullet_list(analysis.get("recommended_angles", [])),
        "",
    ]
    return "\n".join(lines)


def save_analysis(
    analysis: dict[str, Any],
    applications_dir: Path = DEFAULT_APPLICATIONS_DIR,
) -> tuple[Path, Path]:
    """Persist `analysis.json` and `analysis.md` under `applications/<opening_id>/`."""
    opening_id = str(analysis.get("opening_id") or "").strip()
    if not opening_id or "/" in opening_id or "\\" in opening_id or ".." in opening_id:
        raise ValueError(f"Invalid opening_id for output directory: {opening_id!r}")

    target_dir = Path(applications_dir) / opening_id
    target_dir.mkdir(parents=True, exist_ok=True)

    json_path = target_dir / "analysis.json"
    md_path = target_dir / "analysis.md"

    json_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(format_analysis_markdown(analysis), encoding="utf-8")

    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for fetching/reading a JD and saving alignment analysis."""
    parser = argparse.ArgumentParser(description="Analyze job description alignment against verified dossier.")
    parser.add_argument("--id", required=True, help="Opening ID from data/openings.json")
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--jd-file", type=Path, help="Path to local text/markdown JD file")
    source_group.add_argument("--jd-text", type=str, help="Raw job description text")
    source_group.add_argument("--fetch", action="store_true", help="Fetch JD text from opening apply_url (non-LinkedIn)")
    parser.add_argument("--openings", type=Path, default=DEFAULT_OPENINGS_PATH, help="Path to openings.json")
    parser.add_argument("--applications-dir", type=Path, default=DEFAULT_APPLICATIONS_DIR, help="Output directory")
    parser.add_argument("--candidate", type=Path, default=Path("profile/candidate.json"), help="Path to candidate.json")
    parser.add_argument("--dossier", type=Path, default=Path("profile/master_dossier.md"), help="Path to master_dossier.md")

    args = parser.parse_args(argv)

    opening = load_opening_by_id(args.id, openings_path=args.openings)
    master_profile = load_master_profile(candidate_path=args.candidate, dossier_path=args.dossier)

    if args.jd_file is not None:
        jd_text = args.jd_file.read_text(encoding="utf-8")
    elif args.jd_text is not None:
        jd_text = args.jd_text
    elif args.fetch:
        jd_text = fetch_jd_text(opening.get("apply_url", ""))
    else:
        jd_parts = [
            str(opening.get("title") or ""),
            str(opening.get("team") or ""),
            str(opening.get("fit_rationale") or ""),
            " ".join(str(s) for s in opening.get("skills_matched", [])),
        ]
        jd_text = "\n".join(part for part in jd_parts if part.strip())

    analysis = analyze_jd(opening, jd_text, master_profile)
    json_path, md_path = save_analysis(analysis, applications_dir=args.applications_dir)

    print(f"Analyzed {opening.get('id')} ({opening.get('company')} — {opening.get('title')})")
    print(f"Matched skills ({len(analysis['matched_skills'])}): {', '.join(analysis['matched_skills']) or 'None'}")
    print(f"Matched standards ({len(analysis['matched_standards'])}): {', '.join(analysis['matched_standards']) or 'None'}")
    print(f"Skill gaps ({len(analysis['skill_gaps'])}): {', '.join(analysis['skill_gaps']) or 'None'}")
    print(f"Saved: {json_path} and {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
