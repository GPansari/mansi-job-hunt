"""Job Fit Scoring Engine.

Scores job opportunities against candidate profile criteria based on:
- Excluded keywords (instant disqualification: fit_score=1, passed_gate=False)
- Title alignment (+1.5 score)
- Core & verified dossier skills match (+0.5 per skill, max +2.5)
- Target aerospace domain alignment (+0.5 bonus when matched)
- Location preference (Bangalore / Bengaluru: +1.0; other: -1.0)
- Baseline score: 1.0 (clamped 1-5)
Gate passes if fit_score >= 3 and no excluded keywords triggered.
"""

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure repo root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.sync_tracker import sync_json_to_markdown
except ModuleNotFoundError:
    from sync_tracker import sync_json_to_markdown  # type: ignore

DEFAULT_CANDIDATE_PATH = Path("profile/candidate.json")

STOP_WORDS = {
    "and", "or", "&", "in", "of", "for", "the", "a", "an",
    "-", "/", "to", "at", "area", "with", "on", "by"
}

MASTER_DOSSIER_EXTRA_SKILLS: List[str] = [
    "MSOSA",
    "DESE",
    "ReqHub",
    "DataHub",
    "AS9100",
    "SysML v2",
    "ARINC 429",
    "AFDX",
]

SKILL_ALIASES: Dict[str, List[str]] = {
    "IBM DOORS": ["IBM DOORS", "DOORS", "DOORS Next", "DNG"],
    "DOORS": ["DOORS", "IBM DOORS", "DOORS Next", "DNG"],
    "Cameo": ["Cameo", "Cameo Systems Modeler", "Cameo Enterprise Modeler", "No Magic Cameo", "NoMagic", "CATIA Magic"],
    "MagicDraw": ["MagicDraw", "Magic Draw", "No Magic"],
    "3DEXPERIENCE": ["3DEXPERIENCE", "3D Experience", "3DS"],
    "V&V": ["V&V", "V & V", "Verification & Validation", "Verification and Validation", "IVVQ"],
    "ARP4754A": ["ARP4754A", "ARP4754", "ARP 4754A", "ARP 4754", "ARP-4754", "ED-79A"],
    "ARP4761": ["ARP4761", "ARP 4761", "ARP-4761"],
    "DO-178C": ["DO-178C", "DO 178C", "DO178C", "DO-178", "DO-178B/C"],
    "DO-254": ["DO-254", "DO 254", "DO254"],
    "Digital Thread": ["Digital Thread", "Digital Engineering", "DTx"],
    "MSOSA": ["MSOSA"],
    "DESE": ["DESE"],
    "ReqHub": ["ReqHub", "Req Hub"],
    "DataHub": ["DataHub", "Data Hub"],
    "AS9100": ["AS9100", "AS 9100", "AS9100D"],
    "SysML v2": ["SysML v2", "SysMLv2", "SysML 2.0", "SysML v2.0"],
    "ARINC 429": ["ARINC 429", "ARINC-429", "ARINC429"],
    "AFDX": ["AFDX", "ARINC 664", "ARINC-664"],
}

DOMAIN_ALIASES: Dict[str, List[str]] = {
    "Commercial Aircraft": ["commercial aircraft", "commercial aviation", "airliner", "aircraft"],
    "UAV": ["uav", "unmanned aerial", "unmanned aircraft", "drone", "uas", "haps"],
    "eVTOL": ["evtol", "urban air mobility", "advanced air mobility", "aam"],
    "Spacetech": ["spacetech", "satellite", "spacecraft", "orbital", "launch vehicle"],
    "Defense Aerospace": ["defense aerospace", "defence aerospace", "avionics", "aerospace", "flight control"],
}


def load_candidate_profile(profile_path: Optional[Path | str] = None) -> dict:
    """Load candidate profile JSON from specified path or default location."""
    path = Path(profile_path) if profile_path else DEFAULT_CANDIDATE_PATH
    if not path.exists():
        # Fallback to repo root relative resolution if run from subdirectory
        repo_root = Path(__file__).resolve().parent.parent
        alt_path = repo_root / path
        if alt_path.exists():
            path = alt_path
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _tokenize_title(title: str) -> List[str]:
    """Tokenize and normalize title words with light stemming."""
    words = re.findall(r"[A-Za-z0-9+]+", title.lower())
    tokens: List[str] = []
    for w in words:
        if w in STOP_WORDS:
            continue
        # Light stemming for seniority and engineering roles
        if w.endswith("ers") and len(w) > 4:
            w = w[:-3]
        elif w.endswith("er") and len(w) > 4:
            w = w[:-2]  # leader -> lead, manager -> manag
        elif w.endswith("ing") and len(w) > 5:
            w = w[:-3]  # engineering -> engineer
        elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            w = w[:-1]  # systems -> system
        tokens.append(w)
    return tokens


def match_title(job_title: str, target_titles: List[str]) -> Tuple[bool, str]:
    """Check if job title matches any of the candidate target titles."""
    if not job_title or not target_titles:
        return False, ""

    job_lower = job_title.lower().strip()
    job_tokens = set(_tokenize_title(job_title))

    for target in target_titles:
        target_lower = target.lower().strip()
        # Direct substring match
        if target_lower in job_lower or (len(job_lower.split()) >= 2 and job_lower in target_lower):
            return True, target

        target_tokens = set(_tokenize_title(target))
        if not target_tokens:
            continue

        matched_tokens = target_tokens.intersection(job_tokens)

        # 1-token target: exact match required
        if len(target_tokens) == 1 and target_tokens.issubset(job_tokens):
            return True, target
        # Multi-token target: 100% match
        elif len(matched_tokens) == len(target_tokens):
            return True, target
        # Multi-token target: high overlap (at least 2 tokens and >= 60%)
        elif len(matched_tokens) >= 2 and (len(matched_tokens) / len(target_tokens)) >= 0.6:
            return True, target

    return False, ""


def check_excluded_keywords(text: str, excluded_keywords: List[str]) -> List[str]:
    """Check if any excluded keyword is present in text using boundary checks."""
    if not text or not excluded_keywords:
        return []

    matched: List[str] = []
    for kw in excluded_keywords:
        kw_clean = kw.strip()
        if not kw_clean:
            continue
        pattern = r"(?<!\w)" + re.escape(kw_clean) + r"(?!\w)"
        if re.search(pattern, text, re.IGNORECASE):
            matched.append(kw_clean)
    return matched


def match_skills(text: str, core_skills: List[str]) -> List[str]:
    """Identify matched core and verified dossier skills in text using boundary checks."""
    if not text or not core_skills:
        return []

    matched: List[str] = []
    seen_cf: set[str] = set()
    for skill in core_skills:
        skill_clean = skill.strip()
        if not skill_clean or skill_clean.casefold() in seen_cf:
            continue

        # Look for primary skill name and known aliases
        variants = SKILL_ALIASES.get(skill_clean, [skill_clean])
        if skill_clean not in variants:
            variants = [skill_clean] + variants

        for variant in variants:
            pattern = r"(?<!\w)" + re.escape(variant) + r"(?!\w)"
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(skill_clean)
                seen_cf.add(skill_clean.casefold())
                break

    return matched


def match_domains(text: str, target_domains: List[str]) -> List[str]:
    """Identify matched target aerospace domains in text."""
    if not text or not target_domains:
        return []

    matched: List[str] = []
    seen_cf: set[str] = set()
    for domain in target_domains:
        dom_clean = domain.strip()
        if not dom_clean or dom_clean.casefold() in seen_cf:
            continue
        variants = DOMAIN_ALIASES.get(dom_clean, [dom_clean])
        if dom_clean not in variants:
            variants = [dom_clean] + variants
        for variant in variants:
            pattern = r"(?<!\w)" + re.escape(variant) + r"(?!\w)"
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(dom_clean)
                seen_cf.add(dom_clean.casefold())
                break
    return matched


def match_location(job_location: Optional[str], target_locations: List[str]) -> bool:
    """Check if job location matches target locations (defaulting to Bangalore / Bengaluru)."""
    if not job_location:
        return False

    loc_str = str(job_location).lower()
    targets = [t.lower() for t in target_locations] if target_locations else ["bangalore", "bengaluru"]

    if "bangalore" in loc_str or "bengaluru" in loc_str:
        return True

    for target in targets:
        if target in loc_str:
            return True

    return False


def score_job(job_dict: Dict[str, Any], candidate_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Score a job posting against candidate criteria.

    Args:
        job_dict: Job opening details containing title, description, location, etc.
        candidate_profile: Optional candidate profile dict. If None, loads from profile/candidate.json.

    Returns:
        Dict containing:
            fit_score: int (clamped 1-5)
            skills_matched: list of str
            domains_matched: list of str
            fit_rationale: str
            passed_gate: bool (True if fit_score >= 3 and no excluded keywords triggered)
    """
    if candidate_profile is None:
        candidate_profile = load_candidate_profile()

    job_title = job_dict.get("title", "") or ""
    job_desc = job_dict.get("description", "") or ""
    job_loc = job_dict.get("location", "") or ""
    full_text = f"{job_title} {job_desc}"

    excluded_keywords = candidate_profile.get("excluded_keywords", [])
    target_titles = candidate_profile.get("target_titles", [])
    base_skills = list(candidate_profile.get("core_skills", []))
    # Always include verified skills from master_dossier.md without duplicating
    seen_skills = {s.casefold() for s in base_skills}
    for extra in MASTER_DOSSIER_EXTRA_SKILLS:
        if extra.casefold() not in seen_skills:
            base_skills.append(extra)
            seen_skills.add(extra.casefold())

    target_domains = candidate_profile.get("target_domains", [])
    target_locations = candidate_profile.get("target_locations", ["Bangalore", "Bengaluru"])

    # 1. Excluded keywords check (triggers immediate fit_score 1 and passed_gate = False)
    matched_exclusions = check_excluded_keywords(full_text, excluded_keywords)
    if matched_exclusions:
        return {
            "fit_score": 1,
            "skills_matched": [],
            "domains_matched": [],
            "fit_rationale": f"Disqualified: excluded keyword(s) found ({', '.join(matched_exclusions)}).",
            "passed_gate": False,
        }

    # 2. Baseline score: 1.0
    raw_score = 1.0
    rationale_parts: List[str] = []

    # 3. Title match (+1.5 score)
    title_matched, matched_target = match_title(job_title, target_titles)
    if title_matched:
        raw_score += 1.5
        rationale_parts.append(f"Title matched target ('{matched_target}', +1.5)")
    else:
        rationale_parts.append("Title did not match target roles")

    # 4. Core & dossier skills match (+0.5 per skill, max +2.5)
    matched_skills = match_skills(full_text, base_skills)
    skills_score = min(2.5, len(matched_skills) * 0.5)
    raw_score += skills_score
    if matched_skills:
        rationale_parts.append(f"Core skills matched ({len(matched_skills)}: {', '.join(matched_skills)}, +{skills_score:.1f})")
    else:
        rationale_parts.append("No core skills matched")

    # 5. Target aerospace domain bonus (+0.5 max)
    matched_domains = match_domains(full_text, target_domains)
    if matched_domains:
        raw_score += 0.5
        rationale_parts.append(f"Domain matched ({', '.join(matched_domains)}, +0.5)")

    # 6. Location match (Bangalore: +1.0; other: -1.0)
    loc_matched = match_location(job_loc, target_locations)
    if loc_matched:
        raw_score += 1.0
        rationale_parts.append(f"Location '{job_loc}' matches Bangalore (+1.0)")
    else:
        raw_score -= 1.0
        loc_display = job_loc if job_loc else "Unspecified"
        rationale_parts.append(f"Location '{loc_display}' outside Bangalore (-1.0)")

    # 7. Clamping between 1 and 5
    clamped_score = max(1.0, min(5.0, raw_score))
    fit_score = int(round(clamped_score))
    fit_score = max(1, min(5, fit_score))

    # Guardrail: roles with 0 matched skills must at least carry an explicit
    # aerospace/systems engineering title keyword to pass the gate.
    eng_title_pattern = re.compile(
        r"\b(mbse|sysml|systems?|avionics|aerospace|aircraft|uav|evtol|drone|spacecraft|satellite|flight|v&v|ivvq|simulation|digital\s+engineering|architect(?:ure)?)\b",
        re.IGNORECASE,
    )
    if not matched_skills and not eng_title_pattern.search(job_title):
        fit_score = min(fit_score, 2)
        rationale_parts.append("No core skills or aerospace/systems title keyword matched (capped <= 2)")

    # Gate passes if fit_score >= 3 and no excluded keywords
    passed_gate = (fit_score >= 3)

    fit_rationale = "; ".join(rationale_parts) + f". Final fit score: {fit_score}/5."

    return {
        "fit_score": fit_score,
        "skills_matched": matched_skills,
        "domains_matched": matched_domains,
        "fit_rationale": fit_rationale,
        "passed_gate": passed_gate,
    }


def main() -> None:
    """CLI entrypoint for testing and batch scoring openings."""
    parser = argparse.ArgumentParser(description="Job Fit Scoring Engine")
    parser.add_argument("--job-json", help="JSON string representing a single job dict to score")
    parser.add_argument("--profile", help="Path to custom candidate profile JSON")
    parser.add_argument(
        "--score-openings",
        "--score-all",
        dest="score_openings",
        action="store_true",
        help="Score all openings in data/openings.json and report summary",
    )
    parser.add_argument(
        "--update",
        "--save",
        dest="update",
        action="store_true",
        help="Update fit_score, fit_rationale, and skills_matched in data/openings.json and sync to data/Openings_Tracker.md",
    )
    parser.add_argument(
        "--openings",
        help="Path to openings JSON file (default: data/openings.json)",
    )
    parser.add_argument(
        "--tracker",
        help="Path to tracker Markdown file (default: data/Openings_Tracker.md)",
    )
    args = parser.parse_args()

    candidate = load_candidate_profile(args.profile)

    if args.job_json:
        job = json.loads(args.job_json)
        result = score_job(job, candidate)
        print(json.dumps(result, indent=2))
        return

    if args.score_openings or args.update:
        openings_path = Path(args.openings) if args.openings else Path("data/openings.json")
        if not openings_path.exists():
            repo_root = Path(__file__).resolve().parent.parent
            alt_path = repo_root / openings_path
            if alt_path.exists():
                openings_path = alt_path
        if not openings_path.exists():
            print(f"Error: {openings_path} not found.")
            return
        with open(openings_path, "r", encoding="utf-8") as f:
            openings = json.load(f)

        passed = 0
        total = len(openings)
        print(f"Scoring {total} openings from {openings_path}...")
        for op in openings:
            res = score_job(op, candidate)
            if res["passed_gate"]:
                passed += 1
            if args.update:
                op["fit_score"] = res["fit_score"]
                op["fit_rationale"] = res["fit_rationale"]
                op["skills_matched"] = res["skills_matched"]
            print(f"[{res['fit_score']}/5] (Gate: {'PASS' if res['passed_gate'] else 'FAIL'}) {op.get('company')}: {op.get('title')} ({op.get('location')})")

        if args.update:
            with open(openings_path, "w", encoding="utf-8") as f:
                json.dump(openings, f, indent=2, ensure_ascii=False)
                f.write("\n")
            print(f"Updated {total} openings in {openings_path}.")

            tracker_path = Path(args.tracker) if args.tracker else Path("data/Openings_Tracker.md")
            if not tracker_path.exists() and not tracker_path.is_absolute():
                repo_root = Path(__file__).resolve().parent.parent
                alt_tracker = repo_root / tracker_path
                if alt_tracker.parent.exists():
                    tracker_path = alt_tracker
            if sync_json_to_markdown:
                sync_json_to_markdown(openings_path, tracker_path)
                print(f"Synchronized Markdown tracker to {tracker_path}.")

        print(f"\nSummary: {passed}/{total} openings passed gate (fit_score >= 3).")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
