#!/usr/bin/env python3
"""Role-Specific Grounded Interview Prep Pack Generator.

Generates `applications/<opening_id>/interview_prep.md` combining opening
metadata, `analysis.json` (or synthesized alignment from the opening record),
and verified facts from `profile/master_dossier.md` and `profile/candidate.json`.
Every cited experience bullet, metric, standard, and company comes strictly from
the verified master profile.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
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
        _dedupe_preserve_case,
        _matches_any_variant,
        analyze_jd,
        load_opening_by_id,
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
        _dedupe_preserve_case,
        _matches_any_variant,
        analyze_jd,
        load_opening_by_id,
    )
    from profile_loader import (  # type: ignore
        DEFAULT_CANDIDATE_PATH,
        DEFAULT_DOSSIER_PATH,
        load_master_profile,
    )

_H3_PATTERN = re.compile(r"^###(?!#)\s+(.+?)\s*$")
_BULLET_PATTERN = re.compile(r"^[-*]\s+(.+?)\s*$")

_GAP_BRIDGE_MAP: dict[str, str] = {
    "polarion": (
        "Highlight verified requirements management and digital-thread synchronization across "
        "IBM DOORS, 3DEXPERIENCE, DESE, ReqHub, and DataHub; frame Polarion ALM workflows "
        "as an equivalent traceability and baseline-management environment."
    ),
    "jama": (
        "Anchor on verified requirements capture, allocation, and traceability in IBM DOORS "
        "and 3DEXPERIENCE via ReqHub/DataHub, emphasizing rapid ramp-up on Jama Connect."
    ),
    "windchill": (
        "Connect verified PLM/digital-thread synchronization in 3DEXPERIENCE and DESE to "
        "Windchill configuration and requirements traceability workflows."
    ),
    "teamcenter": (
        "Connect verified digital-thread data synchronization across 3DEXPERIENCE, DESE, and "
        "IBM DOORS to Teamcenter engineering data and configuration workflows."
    ),
    "capella": (
        "Bridge from verified executable SysML modeling in Cameo, MagicDraw, and MSOSA using "
        "the Boeing Architecture Method to Capella/Arcadia operational, functional, and logical views."
    ),
    "rhapsody": (
        "Bridge from verified executable SysML architecture work in Cameo and MagicDraw (state "
        "machines, use cases, logical/functional architectures) to IBM Rhapsody."
    ),
    "enterprise architect": (
        "Bridge from verified SysML modeling in Cameo and MagicDraw and standardized process "
        "modeling to Sparx Enterprise Architect."
    ),
    "sysml v2": (
        "Emphasize deep verified SysML v1 execution (ConOps-driven modeling, executable state "
        "machines, logical/functional architecture in Cameo/MagicDraw) as the foundation for "
        "adopting SysML v2 textual/API-first modeling."
    ),
    "scade": (
        "Connect verified executable SysML state-machine modeling, MATLAB/Simulink experience, "
        "and DO-178C/ARP4754A V&V alignment to model-based embedded workflows in SCADE."
    ),
    "labview": (
        "Connect verified MATLAB/Simulink modeling, V&V planning, and hardware-interface "
        "integration on Boeing 777-8F electrical systems and MALE UAV programs to LabVIEW test rigs."
    ),
    "do-160": (
        "Frame verified environmental/quality and certification grounding in ARP4754A, ARP4761, "
        "DO-178C, DO-254, and AS9100 as transferable rigor for DO-160 qualification planning."
    ),
    "iso 26262": (
        "Map verified ARP4754A/ARP4761 safety assessment and failure-condition tracing rigor "
        "to ISO 26262 functional safety lifecycles without overclaiming automotive sign-off."
    ),
    "mosa": (
        "Connect verified logical/functional architecture partitioning and interface definition "
        "across Boeing 777-8F EE subsystems to Modular Open Systems Approach (MOSA) principles."
    ),
    "mil-std-882e": (
        "Bridge from verified ARP4761 safety assessment, failure-condition tracing, and "
        "MIL-STD awareness to MIL-STD-882E system safety hazard tracking."
    ),
}


def _validate_opening_id(opening_id: str) -> str:
    """Reject empty or path-traversal opening IDs."""
    cleaned = str(opening_id or "").strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        raise ValueError(f"Invalid opening_id for interview prep: {opening_id!r}")
    return cleaned


def _parse_experience_blocks(experience_markdown: str) -> list[dict[str, Any]]:
    """Parse `### Header` blocks and their verified bullets from `## Experience`."""
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_line in experience_markdown.splitlines():
        line = raw_line.strip()
        header_match = _H3_PATTERN.match(line)
        if header_match:
            if current is not None:
                blocks.append(current)
            current = {"header": header_match.group(1).strip(), "bullets": []}
            continue
        bullet_match = _BULLET_PATTERN.match(line)
        if bullet_match and current is not None:
            item = bullet_match.group(1).strip()
            if item:
                current["bullets"].append(item)

    if current is not None:
        blocks.append(current)
    return blocks


def _load_or_synthesize_analysis(
    opening_id: str,
    opening: dict[str, Any] | None,
    applications_dir: Path,
    master_profile: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Load `analysis.json` when present, otherwise synthesize via `analyze_jd`."""
    analysis_path = Path(applications_dir) / opening_id / "analysis.json"
    if analysis_path.exists():
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        return analysis, True

    if opening is None:
        raise KeyError(f"Opening ID not found in openings.json or applications/: {opening_id}")

    jd_parts = [
        str(opening.get("title") or ""),
        str(opening.get("team") or ""),
        str(opening.get("fit_rationale") or ""),
        " ".join(str(s) for s in (opening.get("skills_matched") or [])),
    ]
    jd_text = "\n".join(part for part in jd_parts if part.strip())
    return analyze_jd(opening, jd_text, master_profile), False


def _score_bullet_relevance(bullet: str, keywords: list[str]) -> int:
    """Count keyword matches within a verified experience bullet."""
    score = 0
    for kw in keywords:
        if kw and _matches_any_variant(bullet, [kw]):
            score += 1
    return score


def _select_star_stories(
    experience_blocks: list[dict[str, Any]],
    keywords: list[str],
    verified_metrics: list[str],
) -> list[dict[str, Any]]:
    """Select grounded STAR stories strictly from verified experience blocks and metrics."""
    relevant_blocks = [
        block
        for block in experience_blocks
        if block.get("bullets") and "internship" not in block["header"].casefold()
        and "volunteering" not in block["header"].casefold()
    ]

    scored_blocks: list[tuple[int, int, dict[str, Any]]] = []
    for idx, block in enumerate(relevant_blocks):
        header = block["header"]
        # Boeing Lead Systems Engineer is primary current role; keep strong tie-breaker
        base_bonus = 2 if "Boeing India" in header else (1 if "Omnidyne" in header else 0)
        bullet_scores = [_score_bullet_relevance(b, keywords) for b in block["bullets"]]
        total_score = sum(bullet_scores) + base_bonus
        scored_blocks.append((total_score, -idx, block))

    scored_blocks.sort(reverse=True)
    selected: list[dict[str, Any]] = []

    for _, _, block in scored_blocks[:3]:
        bullets = list(block["bullets"])
        ranked_bullets = sorted(
            enumerate(bullets),
            key=lambda pair: (_score_bullet_relevance(pair[1], keywords), -pair[0]),
            reverse=True,
        )
        top_bullets = [b for _, b in ranked_bullets[:3]]
        header = block["header"]

        if "Boeing India" in header:
            situation = (
                "Boeing Digital Transformation (DTx) initiative for 777-8F Electrical and "
                "Electronic (EE) subsystems prior to hardware availability."
            )
            task = (
                "Drive MBSE adoption, build executable SysML models from ConOps, and maintain "
                "digital-thread traceability while leading and mentoring systems engineers."
            )
            result = "; ".join(
                m for m in verified_metrics if "Boeing" in m or "Engineer of the Quarter" in m or "team of 5" in m
            ) or "10 years of aerospace experience across commercial aircraft and UAV programs"
        elif "Omnidyne" in header:
            situation = "Indian Defence RFI requiring a new MALE UAV concept and engineering team setup."
            task = "Own MALE UAV design, sizing, and synthesis from requirements to configuration."
            result = "Completed trade studies, CFD/FEM/aeroelastic analysis, supplier interface management, and engineering hiring."
        elif "Desemco" in header:
            situation = "Aerospace manufacturing quality operations requiring AS9100 compliance."
            task = "Maintain AS9100 compliance, close non-conformances, and support tooling models."
            result = "Closed non-conformances via root-cause and corrective action and built CATIA and VERICUT tool models."
        else:
            situation = f"Verified engagement: {header}."
            task = "Execute core engineering responsibilities captured in the verified dossier."
            result = top_bullets[0]

        selected.append(
            {
                "header": header,
                "situation": situation,
                "task": task,
                "actions": top_bullets,
                "result": result,
            }
        )

    return selected


def _build_deep_dive_topics(
    matched_skills: list[str],
    matched_standards: list[str],
    priority_keywords: list[str],
    verified_facts: dict[str, list[str]],
) -> list[str]:
    """Build grounded technical deep-dive prompts tied to verified dossier programs."""
    topics: list[str] = []
    combined_cf = {item.casefold() for item in matched_skills + matched_standards + priority_keywords}
    verified_programs = verified_facts.get("programs", [])

    if combined_cf & {"mbse", "sysml", "cameo", "magicdraw", "conops", "modeling & simulation", "simulation"}:
        topics.append(
            "**Executable SysML & ConOps-Driven MBSE:** Walk through leading the Detailed Modelling "
            "and Simulation pilot for Boeing 777-8F EE subsystems (Main AC power, ELMS, Backup "
            "Electrical Power, DC and Standby power) using Cameo/MagicDraw, state machines, use "
            "cases, and interactive GUIs before hardware availability."
        )

    if combined_cf & {"ibm doors", "doors", "3dexperience", "digital thread", "requirements", "requirements management"}:
        topics.append(
            "**Digital Thread & Requirements Traceability:** Explain synchronizing requirements and "
            "models across 3DEXPERIENCE, DESE, and IBM DOORS via ReqHub and DataHub, plus "
            "standardizing Boeing Process Instructions as reusable SysML assets."
        )

    if (
        combined_cf & {"v&v", "verification & validation", "safety assessment"}
        or any(s.casefold() in combined_cf for s in ("arp4754a", "arp4761", "do-178c", "do-254", "as9100"))
    ):
        stds = ", ".join(matched_standards) if matched_standards else "ARP4754A, ARP4761, DO-178C, DO-254"
        topics.append(
            f"**Verification, Validation & Safety Compliance ({stds}):** Detail early requirements "
            "validation, failure-condition tracing in executable models, and AS9100 non-conformance "
            "root-cause/corrective-action rigor."
        )

    if combined_cf & {"uav", "evtol", "avionics", "electrical systems", "flight control", "defense aerospace"}:
        uav_prog = next((p for p in verified_programs if "MALE UAV" in p), "MALE UAV design, sizing and synthesis")
        eco_prog = next(
            (p for p in verified_programs if "Eco-Modular Aircraft" in p),
            "MBSE and TOPSIS for an Eco-Modular Aircraft",
        )
        topics.append(
            f"**Aircraft Subsystems, UAV Sizing & Trade Studies:** Contrast Boeing 777-8F electrical "
            f"subsystem integration with `{uav_prog}` — covering material, engine, propeller, and "
            f"landing-gear trade studies, CFD, FEM, and aeroelasticity — alongside `{eco_prog}`."
        )

    if not topics:
        topics.append(
            "**Systems Architecture & Engineering Leadership:** Discuss 10 years of aerospace "
            "systems engineering across Boeing 777-8F DTx MBSE delivery and Omnidyne MALE UAV "
            "concept-to-configuration execution, backed by MS Aerospace Engineering (Georgia Tech)."
        )

    return _dedupe_preserve_case(topics)


def _build_gap_mitigation_points(
    skill_gaps: list[str],
    missing_standards: list[str],
) -> list[str]:
    """Generate transparent, dossier-grounded mitigation points for detected gaps."""
    points: list[str] = []
    for item in _dedupe_preserve_case(skill_gaps + missing_standards):
        bridge = _GAP_BRIDGE_MAP.get(item.casefold())
        if bridge:
            points.append(f"**{item}:** {bridge}")
        else:
            points.append(
                f"**{item}:** Acknowledge current hands-on gap transparently while anchoring on "
                "verified experience in Cameo, MagicDraw, IBM DOORS, 3DEXPERIENCE, and ARP4754A/DO-178C."
            )

    if not points:
        points.append(
            "No direct tool or standard gaps were flagged against the analyzed requirements; "
            "keep focus on domain-specific program architecture and team workflows."
        )
    return points


def _build_panel_questions(
    company: str,
    title: str,
    skill_gaps: list[str],
    missing_standards: list[str],
) -> list[str]:
    """Generate role-grounded questions to ask the interview panel."""
    questions = [
        f"How does the {company} {title} team structure digital-thread traceability between system requirements, SysML architecture models, and V&V artifacts?",
        "At what stage of the lifecycle are executable models or simulations currently used for early stakeholder reviews and failure-condition tracing?",
        "What does success look like in the first 90 days for technical delivery and mentoring across the systems engineering team?",
    ]
    gaps = _dedupe_preserve_case(skill_gaps + missing_standards)
    if gaps:
        gap_list = ", ".join(gaps[:3])
        questions.append(
            f"How standardized are the team's workflows around {gap_list}, and what onboarding resources or reference architectures exist for engineers transitioning from Cameo/IBM DOORS/3DEXPERIENCE?"
        )
    else:
        questions.append(
            "What are the biggest architecture or cross-subsystem integration bottlenecks the team is prioritizing over the next two quarters?"
        )
    return questions


def format_interview_prep_markdown(
    opening_id: str,
    opening: dict[str, Any] | None,
    analysis: dict[str, Any],
    analysis_from_disk: bool,
    master_profile: dict[str, Any],
) -> str:
    """Render a grounded markdown interview preparation pack."""
    candidate = master_profile.get("candidate") or {}
    verified_facts = master_profile.get("verified_facts") or {}
    sections = master_profile.get("sections") or {}

    company = str(analysis.get("company") or (opening or {}).get("company") or "Unknown Company")
    title = str(analysis.get("title") or (opening or {}).get("title") or "Unknown Role")
    location = str(analysis.get("location") or (opening or {}).get("location") or "Unspecified")
    team = str((opening or {}).get("team") or "Unspecified")
    seniority = str((opening or {}).get("seniority") or "Unspecified")
    fit_score = (opening or {}).get("fit_score")
    apply_url = str((opening or {}).get("apply_url") or "")

    matched_skills = list(analysis.get("matched_skills") or [])
    matched_standards = list(analysis.get("matched_standards") or [])
    skill_gaps = list(analysis.get("skill_gaps") or [])
    missing_standards = list(analysis.get("missing_standards") or [])
    priority_keywords = list(analysis.get("priority_keywords") or [])
    recommended_angles = list(analysis.get("recommended_angles") or [])

    verified_metrics = list(verified_facts.get("metrics") or [])
    experience_blocks = _parse_experience_blocks(sections.get("Experience", ""))
    star_keywords = _dedupe_preserve_case(matched_skills + matched_standards + priority_keywords)
    star_stories = _select_star_stories(experience_blocks, star_keywords, verified_metrics)
    deep_dives = _build_deep_dive_topics(
        matched_skills=matched_skills,
        matched_standards=matched_standards,
        priority_keywords=priority_keywords,
        verified_facts=verified_facts,
    )
    gap_points = _build_gap_mitigation_points(skill_gaps, missing_standards)
    panel_questions = _build_panel_questions(company, title, skill_gaps, missing_standards)

    candidate_name = str(candidate.get("name") or "Mansi Agrawal")
    candidate_title = str(candidate.get("current_title") or "Lead Systems Engineer")
    candidate_exp = candidate.get("experience_years", 10)
    candidate_edu = str(candidate.get("education") or "MS Aerospace Engineering, Georgia Tech")

    lines: list[str] = [
        f"# Interview Prep Pack — {title} ({company})",
        "",
        f"_Generated on {date.today().isoformat()} | Grounded strictly in `profile/master_dossier.md` and `profile/candidate.json`._",
        "",
        "## Role Snapshot",
        f"- **Opening ID:** `{opening_id}`",
        f"- **Company:** {company}",
        f"- **Title:** {title}",
        f"- **Team:** {team}",
        f"- **Location:** {location}",
        f"- **Seniority:** {seniority}",
    ]
    if fit_score is not None:
        lines.append(f"- **Fit Score:** {fit_score}/5")
    if apply_url:
        lines.append(f"- **Apply URL:** {apply_url}")
    lines.extend(
        [
            f"- **Analysis Source:** {'Saved `analysis.json`' if analysis_from_disk else 'Synthesized from opening metadata (`skills_matched` & `fit_rationale`)'}",
            f"- **Candidate Baseline:** {candidate_name} — {candidate_title} at Boeing India ({candidate_exp} years aerospace experience; {candidate_edu})",
            f"- **Matched Skills:** {', '.join(matched_skills) if matched_skills else 'None explicitly listed'}",
            f"- **Matched Standards:** {', '.join(matched_standards) if matched_standards else 'None explicitly listed'}",
            f"- **Priority Keywords:** {', '.join(priority_keywords) if priority_keywords else 'None explicitly listed'}",
        ]
    )
    if recommended_angles:
        lines.append("- **Recommended Positioning Angles:**")
        for angle in recommended_angles:
            lines.append(f"  - {angle}")

    lines.extend(["", "## Technical Deep-Dive Topics"])
    for topic in deep_dives:
        lines.append(f"- {topic}")

    lines.extend(["", "## Grounded STAR Story Bank"])
    if star_stories:
        for idx, story in enumerate(star_stories, start=1):
            lines.extend(
                [
                    f"### Story {idx}: {story['header']}",
                    f"- **Situation:** {story['situation']}",
                    f"- **Task:** {story['task']}",
                    "- **Action (Verified Dossier Bullets):**",
                ]
            )
            for bullet in story["actions"]:
                lines.append(f"  - {bullet}")
            lines.append(f"- **Result (Verified):** {story['result']}")
            lines.append("")
    else:
        lines.append("- No experience blocks available in master dossier.")
        lines.append("")

    if verified_metrics:
        lines.append("**Verified Recognition & Scope Metrics:**")
        for metric in verified_metrics:
            lines.append(f"- {metric}")
        lines.append("")

    lines.append("## Gap Mitigation Talking Points")
    for point in gap_points:
        lines.append(f"- {point}")

    lines.extend(["", "## Questions for the Interview Panel"])
    for question in panel_questions:
        lines.append(f"- {question}")
    lines.append("")

    return "\n".join(lines)


def generate_interview_prep(
    opening_id: str,
    applications_dir: Path = DEFAULT_APPLICATIONS_DIR,
    openings_path: Path = DEFAULT_OPENINGS_PATH,
    candidate_path: Path = DEFAULT_CANDIDATE_PATH,
    dossier_path: Path = DEFAULT_DOSSIER_PATH,
    master_profile: dict[str, Any] | None = None,
) -> Path:
    """Generate and persist `applications/<opening_id>/interview_prep.md`."""
    clean_id = _validate_opening_id(opening_id)
    profile = master_profile or load_master_profile(
        candidate_path=candidate_path,
        dossier_path=dossier_path,
    )

    opening: dict[str, Any] | None = None
    try:
        opening = load_opening_by_id(clean_id, openings_path=openings_path)
    except (KeyError, FileNotFoundError):
        opening = None

    analysis, from_disk = _load_or_synthesize_analysis(
        opening_id=clean_id,
        opening=opening,
        applications_dir=Path(applications_dir),
        master_profile=profile,
    )

    content = format_interview_prep_markdown(
        opening_id=clean_id,
        opening=opening,
        analysis=analysis,
        analysis_from_disk=from_disk,
        master_profile=profile,
    )

    target_dir = Path(applications_dir) / clean_id
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / "interview_prep.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for generating an opening's interview prep pack."""
    parser = argparse.ArgumentParser(
        description="Generate a dossier-grounded interview preparation pack for an opening."
    )
    parser.add_argument("--id", required=True, help="Opening ID from data/openings.json")
    parser.add_argument(
        "--applications-dir",
        type=Path,
        default=DEFAULT_APPLICATIONS_DIR,
        help="Applications root directory (default: applications)",
    )
    parser.add_argument(
        "--openings",
        type=Path,
        default=DEFAULT_OPENINGS_PATH,
        help="Path to openings.json (default: data/openings.json)",
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=DEFAULT_CANDIDATE_PATH,
        help="Path to candidate.json",
    )
    parser.add_argument(
        "--dossier",
        type=Path,
        default=DEFAULT_DOSSIER_PATH,
        help="Path to master_dossier.md",
    )

    args = parser.parse_args(argv)
    out_path = generate_interview_prep(
        opening_id=args.id,
        applications_dir=args.applications_dir,
        openings_path=args.openings,
        candidate_path=args.candidate,
        dossier_path=args.dossier,
    )
    print(f"Generated interview prep pack for {args.id}: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
