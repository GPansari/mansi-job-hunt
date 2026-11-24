#!/usr/bin/env python3
"""Multi-Tier Search & Discovery Utilities.

Provides discovery tools for high-fit aerospace engineering opportunities:
1. Tier 1 Google Dorking search query templates targeting public LinkedIn postings
   and public ATS aggregators (Workday, Greenhouse, Lever, Ashby) with zero bot risk.
2. Direct public ATS endpoint query client parsing postings from Workday, Greenhouse,
   Lever, and Ashby into canonical opening records.
3. Automatic scoring and gate verification via `scripts.scorer`.
4. Ingestion and tracker synchronization into `data/openings.json` and `data/Openings_Tracker.md`.
5. Documented LinkedIn human-mimicking safety envelope to prevent account flagging.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

# Ensure repo root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests

try:
    from scripts.scorer import load_candidate_profile, score_job
    from scripts.sync_tracker import sync_json_to_markdown
except ModuleNotFoundError:
    from scorer import load_candidate_profile, score_job  # type: ignore
    from sync_tracker import sync_json_to_markdown  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_CANDIDATE_PATH = Path("profile/candidate.json")
DEFAULT_COMPANIES_PATH = Path("data/target_companies.json")
DEFAULT_OPENINGS_PATH = Path("data/openings.json")
DEFAULT_TRACKER_PATH = Path("data/Openings_Tracker.md")

# ==============================================================================
# LinkedIn Safety Envelope
# Documented parameters for human-mimicking browser behavior to prevent detection
# and avoid IP 999 rate limits.
# ==============================================================================
LINKEDIN_SAFETY_ENVELOPE = {
    "scroll_chunk_min_px": 250,
    "scroll_chunk_max_px": 600,
    "pause_min_sec": 2,
    "pause_max_sec": 6,
    "max_views_per_day": 50,
    "duty_cycle_work_min": 15,
    "duty_cycle_rest_min": 20,
}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _resolve_path(path: Path | str) -> Path:
    """Resolve file path relative to current working directory or repo root."""
    p = Path(path)
    if not p.exists():
        repo_root = Path(__file__).resolve().parent.parent
        alt = repo_root / p
        if alt.exists():
            return alt
    return p


def _make_company_prefix(company_name: str) -> str:
    """Generate uppercase alphanumeric prefix for company ID."""
    if not company_name:
        return "JOB"
    words = re.findall(r"[A-Za-z0-9]+", company_name)
    if not words:
        return "JOB"
    first = words[0].upper()
    if len(first) < 3 and len(words) > 1:
        return f"{first}{words[1].upper()}"[:8]
    return first[:8]


def infer_seniority(title: str) -> str:
    """Infer seniority tier from job title."""
    t = (title or "").lower()
    if "lead" in t and "manager" in t:
        return "Manager/Lead"
    if "director" in t or "head" in t:
        return "Director"
    if "manager" in t:
        return "Manager"
    if "lead" in t or "principal" in t or "staff" in t or "architect" in t:
        return "Lead"
    if "senior" in t or "sr." in t or "sr " in t:
        return "Senior"
    return "Mid/Senior"


# ==============================================================================
# Tier 1: Google Dorking Query Generator
# ==============================================================================

def generate_tier1_dorking_queries(candidate: Optional[dict] = None) -> list[str]:
    """Generate Google Dorking search query templates for public job discovery.

    Targets public LinkedIn job postings and public ATS career boards
    for aerospace MBSE and Systems Engineering roles in Bangalore.

    Args:
        candidate: Candidate profile dict with keys like `core_skills`,
                   `target_locations`, `target_titles`, `target_domains`.
                   Defaults to profile/candidate.json if omitted or empty.

    Returns:
        List of unique, ready-to-use search query strings.
    """
    if not candidate:
        loaded = load_candidate_profile()
        candidate = loaded if loaded else {}

    skills = candidate.get("core_skills") or [
        "MBSE", "SysML", "Cameo", "DOORS", "ARP4754A", "V&V"
    ]
    locations = candidate.get("target_locations") or ["Bangalore", "Bengaluru"]
    titles = candidate.get("target_titles") or [
        "Lead Systems Engineer", "MBSE Lead Engineer", "Systems Architecture Manager"
    ]
    domains = candidate.get("target_domains") or [
        "Commercial Aircraft", "UAV", "eVTOL", "Spacetech", "Defense Aerospace"
    ]

    loc_clause = " OR ".join(f'"{loc}"' for loc in locations)
    loc_group = f"({loc_clause})"

    queries: list[str] = []

    # 1. LinkedIn public jobs - Core MBSE & Modeling Skills
    mbse_skills = [s for s in ["MBSE", "SysML", "Cameo", "MagicDraw"] if s in skills]
    if not mbse_skills:
        mbse_skills = ["MBSE", "SysML"]
    skill_str_1 = " OR ".join(f'"{s}"' for s in mbse_skills[:4])
    queries.append(f'site:linkedin.com/jobs ({skill_str_1}) {loc_group}')

    # 2. LinkedIn public jobs - Safety & Requirements Standards (ARP4754A, DOORS, V&V, DO-178C)
    avionics_skills = [s for s in ["ARP4754A", "DOORS", "IBM DOORS", "V&V", "DO-178C", "3DEXPERIENCE"] if s in skills]
    if not avionics_skills:
        avionics_skills = ["ARP4754A", "DOORS", "V&V"]
    skill_str_2 = " OR ".join(f'"{s}"' for s in avionics_skills[:4])
    queries.append(f'site:linkedin.com/jobs ({skill_str_2}) {loc_group}')

    # 3. LinkedIn public jobs - Target Titles + Systems Engineering
    title_terms = []
    for t in titles[:3]:
        clean_t = re.sub(r"\s+", " ", t).strip()
        title_terms.append(f'"{clean_t}"')
    if title_terms:
        queries.append(f'site:linkedin.com/jobs ({" OR ".join(title_terms)}) {loc_group}')

    # 4. Direct LinkedIn job posting URLs (fast exact-match index)
    queries.append(f'site:linkedin.com/jobs/view ("MBSE" OR "SysML") {loc_group}')

    # 5. Public Workday portals
    queries.append(f'site:myworkdayjobs.com ("MBSE" OR "SysML" OR "Systems Engineer") {loc_group}')

    # 6. Public Greenhouse boards
    queries.append(f'site:boards.greenhouse.io ("MBSE" OR "SysML" OR "Systems Engineer") {loc_group}')

    # 7. Public Lever boards
    queries.append(f'site:jobs.lever.co ("MBSE" OR "SysML" OR "Systems Engineer") {loc_group}')

    # 8. Public Ashby boards
    queries.append(f'site:jobs.ashbyhq.com ("MBSE" OR "SysML" OR "Systems Engineer") {loc_group}')

    # 9. Aggregator / Aerospace Domain Boards
    domain_terms = " OR ".join(
        f'"{d}"' if " " in d else d
        for d in ["aerospace", "avionics", "commercial aircraft", "UAV", "eVTOL", "spacetech"]
    )
    queries.append(
        f'({domain_terms}) ("MBSE" OR "SysML") {loc_group} (intitle:careers OR intitle:jobs)'
    )

    # Return deduplicated queries preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append(q)

    return deduped


# ==============================================================================
# Tier 2: Public ATS Feed Query Client
# ==============================================================================

def _parse_workday_url(careers_url: str, company: dict) -> Tuple[str, str, str]:
    """Extract host, tenant, and site for Workday CXS endpoints."""
    parsed = urlparse(careers_url)
    host = parsed.netloc

    path_segments = [
        seg for seg in parsed.path.strip("/").split("/")
        if seg and seg not in ("en-US", "en-GB", "en", "job")
    ]

    site = company.get("workday_site")
    tenant = company.get("workday_tenant") or company.get("tenant")

    if not site:
        site = path_segments[-1] if path_segments else company.get("name", "").split()[0]
    if not tenant:
        # Default tenant to site or first segment
        tenant = path_segments[0] if path_segments else site

    return host, tenant, site


def _query_workday(company: dict, timeout: int = 10) -> list[dict]:
    """Query Workday CXS public job search JSON API."""
    careers_url = company.get("careers_url", "").strip()
    if not careers_url:
        return []

    host, tenant, site = _parse_workday_url(careers_url, company)
    endpoint = company.get("feed_url") or company.get("ats_url") or f"https://{host}/wday/cxs/{tenant}/{site}/jobs"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }
    payload = {
        "appliedFacets": {},
        "limit": 20,
        "offset": 0,
        "searchText": company.get("search_text", ""),
    }

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("Workday query returned HTTP %s for %s", resp.status_code, company.get("name"))
            return []
        data = resp.json()
    except Exception as exc:
        logger.warning("Workday query failed for %s: %s", company.get("name"), exc)
        return []

    postings = data.get("jobPostings", [])
    jobs: list[dict] = []
    parsed_base = urlparse(careers_url)

    for p in postings:
        title = p.get("title", "").strip()
        if not title:
            continue

        ext_path = p.get("externalPath", "")
        if ext_path.startswith("http"):
            apply_url = ext_path
        elif ext_path:
            apply_url = f"https://{host}{ext_path}"
        else:
            apply_url = careers_url

        bullet_fields = p.get("bulletFields", [])
        req_id = ""
        # Check bullet fields for requisition format (e.g. JR10400715, 01868963, R12345)
        for b in bullet_fields:
            m = re.search(r"\b(JR\d+|R\d+|\d{6,}|[A-Z0-9_-]{6,})\b", str(b))
            if m:
                req_id = m.group(1)
                break
        if not req_id and ext_path:
            m = re.search(r"_(JR\d+|R\d+|\d{6,}|[A-Z0-9_-]+)(?:-\d+)?$", ext_path)
            if m:
                req_id = m.group(1)

        location = p.get("locationsText")
        if not location and bullet_fields:
            location = str(bullet_fields[-1])
        if not location:
            location = company.get("location", "Bangalore")

        job_family = p.get("jobFamilyGroup", {})
        team = job_family.get("name") if isinstance(job_family, dict) else "Systems Engineering"

        jobs.append({
            "title": title,
            "req_id": req_id,
            "location": location,
            "team": team or "Systems Engineering",
            "apply_url": apply_url,
            "description": f"{title}. Posted: {p.get('postedOn', '')}. {location}.",
            "source_type": "Workday",
        })

    return jobs


def _query_greenhouse(company: dict, timeout: int = 10) -> list[dict]:
    """Query Greenhouse Boards public JSON API."""
    careers_url = company.get("careers_url", "").strip()
    board_token = company.get("board_token")

    if not board_token and careers_url:
        parsed = urlparse(careers_url)
        path_segments = [s for s in parsed.path.strip("/").split("/") if s and s != "embed"]
        if path_segments:
            board_token = path_segments[-1]
        elif parsed.query:
            params = parse_qs(parsed.query)
            if "for" in params:
                board_token = params["for"][0]

    if not board_token:
        board_token = re.sub(r"[^a-z0-9_-]+", "", company.get("name", "").lower())

    endpoint = company.get("feed_url") or f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"

    headers = {
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }

    try:
        resp = requests.get(endpoint, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("Greenhouse query returned HTTP %s for %s", resp.status_code, company.get("name"))
            return []
        data = resp.json()
    except Exception as exc:
        logger.warning("Greenhouse query failed for %s: %s", company.get("name"), exc)
        return []

    jobs_data = data.get("jobs", []) if isinstance(data, dict) else []
    jobs: list[dict] = []

    for j in jobs_data:
        title = j.get("title", "").strip()
        if not title:
            continue

        loc_data = j.get("location")
        loc_str = loc_data.get("name") if isinstance(loc_data, dict) else str(loc_data or "")
        location = loc_str.strip() or company.get("location", "Bangalore")

        req_id = str(j.get("id") or "")
        apply_url = j.get("absolute_url") or careers_url

        departments = j.get("departments", [])
        team = departments[0].get("name") if departments and isinstance(departments[0], dict) else "Engineering"
        description = j.get("content", "") or title

        jobs.append({
            "title": title,
            "req_id": req_id,
            "location": location,
            "team": team or "Engineering",
            "apply_url": apply_url,
            "description": description,
            "source_type": "Greenhouse",
        })

    return jobs


def _query_lever(company: dict, timeout: int = 10) -> list[dict]:
    """Query Lever Postings public JSON API."""
    careers_url = company.get("careers_url", "").strip()
    site = company.get("lever_site") or company.get("board_token")

    if not site and careers_url:
        parsed = urlparse(careers_url)
        path_segments = [s for s in parsed.path.strip("/").split("/") if s]
        if path_segments:
            site = path_segments[0]

    if not site:
        site = re.sub(r"[^a-z0-9_-]+", "", company.get("name", "").lower())

    endpoint = company.get("feed_url") or f"https://api.lever.co/v0/postings/{site}?mode=json"

    headers = {
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }

    try:
        resp = requests.get(endpoint, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("Lever query returned HTTP %s for %s", resp.status_code, company.get("name"))
            return []
        data = resp.json()
    except Exception as exc:
        logger.warning("Lever query failed for %s: %s", company.get("name"), exc)
        return []

    if not isinstance(data, list):
        return []

    jobs: list[dict] = []
    for item in data:
        title = item.get("text", "").strip()
        if not title:
            continue

        req_id = str(item.get("id") or "")
        apply_url = item.get("hostedUrl") or careers_url

        categories = item.get("categories", {})
        location = categories.get("location") or company.get("location", "Bangalore")
        team = categories.get("team") or "Engineering"
        desc = item.get("descriptionPlain") or item.get("description") or title

        jobs.append({
            "title": title,
            "req_id": req_id,
            "location": location,
            "team": team or "Engineering",
            "apply_url": apply_url,
            "description": desc,
            "source_type": "Lever",
        })

    return jobs


def _query_ashby(company: dict, timeout: int = 10) -> list[dict]:
    """Query Ashby Job Board public API."""
    careers_url = company.get("careers_url", "").strip()
    board = company.get("board_token") or company.get("ashby_board")

    if not board and careers_url:
        parsed = urlparse(careers_url)
        path_segments = [s for s in parsed.path.strip("/").split("/") if s]
        if path_segments:
            board = path_segments[0]

    if not board:
        board = re.sub(r"[^a-z0-9_-]+", "", company.get("name", "").lower())

    endpoint = company.get("feed_url") or f"https://api.ashbyhq.com/posting-api/job-board/{board}"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }

    try:
        resp = requests.post(endpoint, json={}, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("Ashby query returned HTTP %s for %s", resp.status_code, company.get("name"))
            return []
        data = resp.json()
    except Exception as exc:
        logger.warning("Ashby query failed for %s: %s", company.get("name"), exc)
        return []

    jobs_data = data.get("jobs", []) if isinstance(data, dict) else []
    jobs: list[dict] = []

    for item in jobs_data:
        title = item.get("title", "").strip()
        if not title:
            continue

        req_id = str(item.get("id") or "")
        apply_url = item.get("jobUrl") or careers_url

        loc = item.get("location")
        location = loc.get("name") if isinstance(loc, dict) else str(loc or company.get("location", "Bangalore"))
        team = item.get("department") or "Engineering"
        desc = item.get("descriptionPlain") or item.get("descriptionHtml") or title

        jobs.append({
            "title": title,
            "req_id": req_id,
            "location": location,
            "team": team or "Engineering",
            "apply_url": apply_url,
            "description": desc,
            "source_type": "Ashby",
        })

    return jobs


def query_public_ats_feed(
    company: dict,
    timeout: int = 10,
    candidate: Optional[dict] = None,
) -> list[dict]:
    """Query public ATS endpoints for target aerospace companies and parse jobs.

    Supports Workday, Greenhouse, Lever, and Ashby public JSON feeds.
    Scores each discovered job against candidate profile using `scripts.scorer`.

    Args:
        company: Target company dict containing `name`, `careers_url`, and `ats_type`.
        timeout: Network request timeout in seconds.
        candidate: Candidate profile dict for scoring (loaded from file if None).

    Returns:
        List of standardized opening dicts matching the repo schema.
    """
    ats_type = (company.get("ats_type") or "").strip().lower()
    careers_url = company.get("careers_url", "").lower()

    raw_jobs: list[dict] = []

    if ats_type == "workday" or "myworkdayjobs.com" in careers_url:
        raw_jobs = _query_workday(company, timeout=timeout)
    elif ats_type == "greenhouse" or "greenhouse.io" in careers_url:
        raw_jobs = _query_greenhouse(company, timeout=timeout)
    elif ats_type == "lever" or "lever.co" in careers_url:
        raw_jobs = _query_lever(company, timeout=timeout)
    elif ats_type == "ashby" or "ashbyhq.com" in careers_url:
        raw_jobs = _query_ashby(company, timeout=timeout)
    else:
        logger.debug("Unsupported or custom ATS for %s (%s)", company.get("name"), ats_type)
        return []

    if not raw_jobs:
        return []

    if candidate is None:
        candidate = load_candidate_profile()

    today_str = datetime.now().strftime("%Y-%m-%d")
    company_name = company.get("name", "Unknown Company")
    company_prefix = _make_company_prefix(company_name)

    standardized: list[dict] = []
    for raw in raw_jobs:
        title = raw.get("title", "")
        req_id = raw.get("req_id", "")

        # Compute consistent ID
        if req_id:
            clean_req = re.sub(r"[^A-Za-z0-9_-]+", "", req_id)
            job_id = f"{company_prefix}-{clean_req}"
        else:
            hashed = hashlib.md5(f"{company_name}_{title}".encode("utf-8")).hexdigest()[:8]
            job_id = f"{company_prefix}-{hashed}"

        # Fit scoring integration
        score_input = {
            "title": title,
            "description": raw.get("description", ""),
            "location": raw.get("location", ""),
        }
        score_res = score_job(score_input, candidate)

        fit_score = score_res["fit_score"]
        passed_gate = score_res["passed_gate"]
        seniority = infer_seniority(title)

        source_label = f"Official ({raw.get('source_type', ats_type.title())})"
        next_action = "Draft tailored resume" if fit_score >= 4 else "Review job description"

        entry = {
            "id": job_id,
            "company": company_name,
            "team": raw.get("team", "Systems Engineering"),
            "title": title,
            "location": raw.get("location", "Bangalore"),
            "req_id": req_id or "-",
            "seniority": seniority,
            "fit_score": fit_score,
            "fit_rationale": score_res["fit_rationale"],
            "skills_matched": score_res["skills_matched"],
            "apply_url": raw.get("apply_url", company.get("careers_url", "")),
            "source": source_label,
            "status": "Not Applied",
            "date_discovered": today_str,
            "last_updated": today_str,
            "next_action": next_action,
            "passed_gate": passed_gate,
        }
        standardized.append(entry)

    return standardized


def scan_all_ats_feeds(
    companies: list[dict],
    candidate: Optional[dict] = None,
    timeout: int = 10,
    company_filter: Optional[str] = None,
) -> list[dict]:
    """Scan all ATS-configured target companies and aggregate openings."""
    supported_ats = {"workday", "greenhouse", "lever", "ashby"}
    all_openings: list[dict] = []

    for c in companies:
        name = c.get("name", "")
        if company_filter and company_filter.lower() not in name.lower():
            continue

        ats_type = (c.get("ats_type") or "").strip().lower()
        careers_url = c.get("careers_url", "").lower()

        # Check if company uses one of the supported public ATS feeds
        is_supported = (
            ats_type in supported_ats
            or any(s in careers_url for s in ("myworkdayjobs.com", "greenhouse.io", "lever.co", "ashbyhq.com"))
            or bool(c.get("feed_url") or c.get("ats_url"))
        )

        if not is_supported:
            continue

        logger.info("Scanning %s (%s)...", name, ats_type or "ATS")
        results = query_public_ats_feed(c, timeout=timeout, candidate=candidate)
        all_openings.extend(results)

    return all_openings


# ==============================================================================
# Ingestion & Tracker Synchronization
# ==============================================================================

def ingest_openings(
    discovered_jobs: list[dict],
    json_path: Path | str = DEFAULT_OPENINGS_PATH,
    md_path: Path | str = DEFAULT_TRACKER_PATH,
    min_fit_score: int = 3,
) -> list[dict]:
    """Append newly discovered passing openings directly to openings.json and sync to Markdown.

    Filters out duplicates by existing ID or apply URL, and only ingests openings
    that pass the gate (fit_score >= min_fit_score).

    Args:
        discovered_jobs: List of standardized job dicts.
        json_path: Path to openings JSON file.
        md_path: Path to Openings_Tracker Markdown file.
        min_fit_score: Minimum fit score threshold (default: 3).

    Returns:
        List of newly added opening dicts.
    """
    json_file = Path(json_path)
    md_file = Path(md_path)

    existing_openings: list[dict] = []
    if json_file.exists():
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                existing_openings = json.load(f)
        except Exception as exc:
            logger.error("Failed to load existing openings from %s: %s", json_file, exc)
            existing_openings = []

    existing_ids: Set[str] = {
        str(op.get("id")) for op in existing_openings if op.get("id")
    }
    existing_urls: Set[str] = {
        str(op.get("apply_url")).strip().rstrip("/")
        for op in existing_openings
        if op.get("apply_url") and op.get("apply_url") != "-"
    }

    newly_added: list[dict] = []
    canonical_keys = [
        "id", "company", "team", "title", "location", "req_id",
        "seniority", "fit_score", "fit_rationale", "skills_matched",
        "apply_url", "source", "status", "date_discovered",
        "last_updated", "next_action"
    ]

    for job in discovered_jobs:
        # Check fit gate
        passed_gate = job.get("passed_gate")
        if passed_gate is None:
            passed_gate = (job.get("fit_score", 0) >= min_fit_score)
        if not passed_gate:
            continue

        job_id = str(job.get("id", "")).strip()
        job_url = str(job.get("apply_url", "")).strip().rstrip("/")

        if not job_id:
            continue
        if job_id in existing_ids:
            logger.debug("Skipping existing opening ID: %s", job_id)
            continue
        if job_url and job_url in existing_urls:
            logger.debug("Skipping existing opening apply URL: %s", job_url)
            continue

        # Format clean canonical dict
        clean_entry = {k: job.get(k) for k in canonical_keys}
        # Ensure non-null required values
        clean_entry["status"] = clean_entry["status"] or "Not Applied"
        clean_entry["skills_matched"] = clean_entry["skills_matched"] or []
        clean_entry["req_id"] = clean_entry["req_id"] or "-"

        existing_openings.append(clean_entry)
        existing_ids.add(job_id)
        if job_url:
            existing_urls.add(job_url)

        newly_added.append(clean_entry)

    if newly_added:
        json_file.parent.mkdir(parents=True, exist_ok=True)
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(existing_openings, f, indent=2, ensure_ascii=False)
            f.write("\n")

        if md_file:
            md_file.parent.mkdir(parents=True, exist_ok=True)
            sync_json_to_markdown(json_file, md_file)

        logger.info(
            "Ingested %d new opening(s) into %s and synced to %s",
            len(newly_added), json_file, md_file
        )

    return newly_added


# ==============================================================================
# CLI Entrypoint
# ==============================================================================

def main() -> None:
    """CLI interface for search engine utilities."""
    parser = argparse.ArgumentParser(
        description="Autonomous Multi-Tier Search & Discovery Engine for Mansi Agrawal"
    )
    parser.add_argument(
        "--queries",
        action="store_true",
        help="Print generated Tier 1 Google Dorking queries for LinkedIn & ATS boards",
    )
    parser.add_argument(
        "--scan-ats",
        action="store_true",
        help="Query configured public ATS endpoints from data/target_companies.json",
    )
    parser.add_argument(
        "--ingest-new",
        action="store_true",
        help="Append newly discovered passing roles directly to data/openings.json and sync Markdown",
    )
    parser.add_argument(
        "--company",
        help="Filter ATS scan to a specific company name (e.g. 'Airbus', 'Collins')",
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_CANDIDATE_PATH,
        help="Path to candidate profile JSON",
    )
    parser.add_argument(
        "--companies-file",
        type=Path,
        default=DEFAULT_COMPANIES_PATH,
        help="Path to target companies JSON",
    )
    parser.add_argument(
        "--openings-file",
        type=Path,
        default=DEFAULT_OPENINGS_PATH,
        help="Path to openings JSON",
    )
    parser.add_argument(
        "--tracker-file",
        type=Path,
        default=DEFAULT_TRACKER_PATH,
        help="Path to Markdown tracker file",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="HTTP request timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate scan and report roles without writing changes to disk",
    )

    args = parser.parse_args()

    candidate = load_candidate_profile(args.profile)
    candidate_name = candidate.get("name", "Mansi Agrawal")

    if args.queries:
        queries = generate_tier1_dorking_queries(candidate)
        print(f"\n=== Tier 1 Google Dorking Queries ({candidate_name}) ===\n")
        for i, q in enumerate(queries, 1):
            print(f"{i:2d}. {q}")
        print("\nNote: Execute these queries in Google Search / browser under standard human browsing.")
        print(f"Safety limits: Max {LINKEDIN_SAFETY_ENVELOPE['max_views_per_day']} views/day; "
              f"pauses of {LINKEDIN_SAFETY_ENVELOPE['pause_min_sec']}–{LINKEDIN_SAFETY_ENVELOPE['pause_max_sec']}s.\n")
        return

    if args.scan_ats or args.ingest_new:
        companies_path = _resolve_path(args.companies_file)
        if not companies_path.exists():
            print(f"Error: Target companies file not found at {companies_path}")
            return

        with open(companies_path, "r", encoding="utf-8") as f:
            companies = json.load(f)

        print(f"\nScanning public ATS endpoints for target companies (Filter: {args.company or 'All'})...")
        discovered = scan_all_ats_feeds(
            companies,
            candidate=candidate,
            timeout=args.timeout,
            company_filter=args.company,
        )

        passed_roles = [r for r in discovered if r.get("passed_gate")]
        print(f"\nDiscovered {len(discovered)} total role(s); {len(passed_roles)} passed fit gate (score >= 3):\n")

        for r in discovered:
            gate_label = "PASS" if r.get("passed_gate") else "FAIL"
            print(
                f"[{r['fit_score']}/5 | {gate_label}] {r['company']} - {r['title']} ({r['location']})\n"
                f"       Req: {r['req_id']} | Source: {r['source']}\n"
                f"       URL: {r['apply_url']}\n"
                f"       Rationale: {r['fit_rationale']}\n"
            )

        if args.ingest_new:
            if args.dry_run:
                print(f"[DRY RUN] Would ingest {len(passed_roles)} passing role(s) to {args.openings_file}.")
            else:
                newly_added = ingest_openings(
                    discovered,
                    json_path=_resolve_path(args.openings_file),
                    md_path=_resolve_path(args.tracker_file),
                )
                print(f"Summary: Ingested {len(newly_added)} new role(s) into openings tracker.")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
