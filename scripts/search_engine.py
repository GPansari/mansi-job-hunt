#!/usr/bin/env python3
"""Multi-Tier Search & Discovery Utilities.

Provides discovery tools for high-fit aerospace engineering opportunities:
1. Tier 1 Google Dorking search query templates targeting public LinkedIn postings
   and public ATS aggregators (Workday, Greenhouse, Lever, Ashby, Kula, Freshteam).
2. Direct public ATS endpoint query client using `requests.Session()` with retry/backoff,
   multi-query Workday search with pagination, Bangalore filtering, and full JD fetch,
   plus Greenhouse, Lever, Ashby, Kula, and Freshteam adapters.
3. Automatic scoring and gate verification via `scripts.scorer`.
4. 3-tier `url_type` ingestion gate (`direct_requisition`, `board_role_anchor`, rejecting
   `generic_portal`) and dual-tracker synchronization.
5. Documented LinkedIn human-mimicking safety envelope to prevent account flagging.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import html as html_lib
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any, Optional, Set, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

# Ensure repo root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from scripts.scorer import load_candidate_profile, score_job
    from scripts.sync_tracker import sync_json_to_markdown
    from scripts.verify_links import classify_url_type, verify_board_role_cta
except ModuleNotFoundError:
    from scorer import load_candidate_profile, score_job  # type: ignore
    from sync_tracker import sync_json_to_markdown  # type: ignore
    from verify_links import classify_url_type, verify_board_role_cta  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_CANDIDATE_PATH = Path("profile/candidate.json")
DEFAULT_COMPANIES_PATH = Path("data/target_companies.json")
DEFAULT_OPENINGS_PATH = Path("data/openings.json")
DEFAULT_TRACKER_PATH = Path("data/Openings_Tracker.md")

# ==============================================================================
# LinkedIn Safety Envelope
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

WORKDAY_DEFAULT_QUERIES: Tuple[str, ...] = (
    "MBSE",
    "SysML",
    "Avionics",
    "V&V",
    "Systems Engineer",
)


def _create_http_session() -> requests.Session:
    """Build a requests.Session with automatic retry and exponential backoff."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "POST"),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": DEFAULT_USER_AGENT})
    return session


def _strip_html(text: str) -> str:
    """Strip HTML tags and decode entities into clean plain text."""
    if not text:
        return ""
    cleaned = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<style\b[^>]*>.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html_lib.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_date_posted(raw_value: Any, reference_date: Optional[date] = None) -> str:
    """Normalize ATS posting dates (ISO, epoch ms, or Workday relative strings) to YYYY-MM-DD."""
    if raw_value is None:
        return ""
    ref = reference_date or datetime.now().date()
    if isinstance(raw_value, (int, float)):
        ts = float(raw_value)
        if ts > 1e11:
            ts /= 1000.0
        if ts > 0:
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return ""
    s = str(raw_value).strip()
    if not s:
        return ""
    m_iso = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m_iso:
        return m_iso.group(1)
    lower = s.lower()
    if "today" in lower:
        return ref.isoformat()
    if "yesterday" in lower:
        return (ref - timedelta(days=1)).isoformat()
    m_days = re.search(r"\b(\d+)\s+days?\s+ago\b", lower)
    if m_days and "+" not in s:
        return (ref - timedelta(days=int(m_days.group(1)))).isoformat()
    return ""


def _is_bangalore_or_india_location(location: str) -> bool:
    """Return True if location matches Bangalore/Bengaluru/India/Remote or is unspecified."""
    loc = (location or "").strip().lower()
    if not loc:
        return True
    allowed = ("bangalore", "bengaluru", "karnataka", "india", "remote", "ind -", "in-ka")
    return any(tok in loc for tok in allowed)


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
    """Generate Google Dorking search query templates for public job discovery."""
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

    mbse_skills = [s for s in ["MBSE", "SysML", "Cameo", "MagicDraw"] if s in skills] or ["MBSE", "SysML"]
    skill_str_1 = " OR ".join(f'"{s}"' for s in mbse_skills[:4])
    queries.append(f'site:linkedin.com/jobs ({skill_str_1}) {loc_group}')

    avionics_skills = [
        s for s in ["ARP4754A", "DOORS", "IBM DOORS", "V&V", "DO-178C", "3DEXPERIENCE"] if s in skills
    ] or ["ARP4754A", "DOORS", "V&V"]
    skill_str_2 = " OR ".join(f'"{s}"' for s in avionics_skills[:4])
    queries.append(f'site:linkedin.com/jobs ({skill_str_2}) {loc_group}')

    title_terms = [f'"{re.sub(r"\\s+", " ", t).strip()}"' for t in titles[:3]]
    if title_terms:
        queries.append(f'site:linkedin.com/jobs ({" OR ".join(title_terms)}) {loc_group}')

    queries.append(f'site:linkedin.com/jobs/view ("MBSE" OR "SysML") {loc_group}')
    queries.append(f'site:myworkdayjobs.com ("MBSE" OR "SysML" OR "Systems Engineer") {loc_group}')
    queries.append(f'site:boards.greenhouse.io ("MBSE" OR "SysML" OR "Systems Engineer") {loc_group}')
    queries.append(f'site:jobs.lever.co ("MBSE" OR "SysML" OR "Systems Engineer") {loc_group}')
    queries.append(f'site:jobs.ashbyhq.com ("MBSE" OR "SysML" OR "Systems Engineer") {loc_group}')

    candidate_domains = [d.lower() for d in domains]
    combined_domains = list(dict.fromkeys(["aerospace", "avionics"] + candidate_domains))
    domain_terms = " OR ".join(f'"{d}"' if " " in d else d for d in combined_domains)
    queries.append(f'({domain_terms}) ("MBSE" OR "SysML") {loc_group} (intitle:careers OR intitle:jobs)')

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
        tenant = path_segments[0] if path_segments else site

    return host, tenant, site


def _fetch_workday_detail(
    session: requests.Session,
    host: str,
    tenant: str,
    site: str,
    ext_path: str,
    timeout: int,
) -> Tuple[str, str]:
    """Fetch full Workday job description text and startDate from CXS detail endpoint."""
    if not ext_path or not ext_path.startswith("/"):
        return "", ""
    detail_url = f"https://{host}/wday/cxs/{tenant}/{site}{ext_path}"
    try:
        resp = session.get(
            detail_url,
            headers={"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT},
            timeout=timeout,
        )
        if resp.status_code != 200:
            return "", ""
        payload = resp.json()
        info = payload.get("jobPostingInfo", {}) if isinstance(payload, dict) else {}
        desc_html = info.get("jobDescription") or info.get("additionalLocations") or ""
        desc_text = _strip_html(desc_html) if isinstance(desc_html, str) else ""
        start_date = parse_date_posted(info.get("startDate"))
        return desc_text, start_date
    except Exception:
        return "", ""


def _fetch_workday_jd(
    session: requests.Session,
    host: str,
    tenant: str,
    site: str,
    ext_path: str,
    timeout: int,
) -> str:
    """Fetch full Workday job description text from CXS detail endpoint."""
    desc_text, _ = _fetch_workday_detail(session, host, tenant, site, ext_path, timeout)
    return desc_text


def _query_workday(
    company: dict,
    timeout: int = 10,
    session: Optional[requests.Session] = None,
    max_pages: int = 2,
) -> list[dict]:
    """Query Workday CXS public job search JSON API with multi-query, pagination, and full JD fetch."""
    careers_url = company.get("careers_url", "").strip()
    if not careers_url:
        return []

    http = session or _create_http_session()
    host, tenant, site = _parse_workday_url(careers_url, company)
    endpoint = company.get("feed_url") or company.get("ats_url") or f"https://{host}/wday/cxs/{tenant}/{site}/jobs"

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": DEFAULT_USER_AGENT,
    }

    custom_search = (company.get("search_text") or "").strip()
    queries = (custom_search,) if custom_search else WORKDAY_DEFAULT_QUERIES

    seen_keys: set[str] = set()
    jobs: list[dict] = []
    limit = 20

    for search_text in queries:
        offset = 0
        for _ in range(max_pages):
            payload = {
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": search_text,
            }
            try:
                resp = http.post(endpoint, json=payload, headers=headers, timeout=timeout)
                if resp.status_code != 200:
                    logger.warning("Workday query '%s' returned HTTP %s for %s", search_text, resp.status_code, company.get("name"))
                    break
                data = resp.json()
            except Exception as exc:
                logger.warning("Workday query '%s' failed for %s: %s", search_text, company.get("name"), exc)
                break

            postings = data.get("jobPostings", [])
            if not postings:
                break

            for p in postings:
                title = p.get("title", "").strip()
                if not title:
                    continue

                ext_path = p.get("externalPath", "")
                if ext_path.startswith("http"):
                    apply_url = ext_path
                elif ext_path:
                    apply_url = f"https://{host}/en-US/{site}{ext_path}" if f"/{site}/" not in ext_path else f"https://{host}{ext_path}"
                else:
                    apply_url = careers_url

                dedupe_key = ext_path or f"{title.lower()}::{apply_url}"
                if dedupe_key in seen_keys:
                    continue

                bullet_fields = p.get("bulletFields", [])
                location = p.get("locationsText")
                if not location and bullet_fields:
                    location = str(bullet_fields[-1])
                if not location:
                    location = company.get("location", "Bangalore")

                # Filter out clearly non-Bangalore/non-India locations
                if not _is_bangalore_or_india_location(location):
                    continue

                seen_keys.add(dedupe_key)

                req_id = ""
                for b in bullet_fields:
                    m = re.search(r"\b(JR\d+|R\d+|\d{6,}|[A-Z0-9_-]{6,})\b", str(b))
                    if m:
                        req_id = m.group(1)
                        break
                if not req_id and ext_path:
                    m = re.search(r"_(JR\d+|R\d+|\d{6,}|[A-Z0-9_-]+)(?:-\d+)?$", ext_path)
                    if m:
                        req_id = m.group(1)

                job_family = p.get("jobFamilyGroup", {})
                team = job_family.get("name") if isinstance(job_family, dict) else "Systems Engineering"

                full_jd, start_date = _fetch_workday_detail(http, host, tenant, site, ext_path, timeout=timeout)
                posted_on = p.get("postedOn", "")
                date_posted = start_date or parse_date_posted(posted_on)
                description = full_jd or f"{title}. Posted: {posted_on}. {location}."

                jobs.append({
                    "title": title,
                    "req_id": req_id,
                    "location": location,
                    "team": team or "Systems Engineering",
                    "apply_url": apply_url,
                    "description": description,
                    "date_posted": date_posted,
                    "source_type": "Workday",
                })

            total = int(data.get("total") or 0)
            offset += limit
            if offset >= total or len(postings) < limit:
                break

    return jobs


def _query_greenhouse(
    company: dict,
    timeout: int = 10,
    session: Optional[requests.Session] = None,
) -> list[dict]:
    """Query Greenhouse Boards public JSON API."""
    http = session or _create_http_session()
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
    headers = {"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT}

    try:
        resp = http.get(endpoint, headers=headers, timeout=timeout)
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
        description = _strip_html(j.get("content", "")) or title
        date_posted = parse_date_posted(j.get("first_published") or j.get("updated_at"))

        jobs.append({
            "title": title,
            "req_id": req_id,
            "location": location,
            "team": team or "Engineering",
            "apply_url": apply_url,
            "description": description,
            "date_posted": date_posted,
            "source_type": "Greenhouse",
        })

    return jobs


def _query_lever(
    company: dict,
    timeout: int = 10,
    session: Optional[requests.Session] = None,
) -> list[dict]:
    """Query Lever Postings public JSON API."""
    http = session or _create_http_session()
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
    headers = {"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT}

    try:
        resp = http.get(endpoint, headers=headers, timeout=timeout)
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
        desc = item.get("descriptionPlain") or _strip_html(item.get("description", "")) or title
        date_posted = parse_date_posted(item.get("createdAt"))

        jobs.append({
            "title": title,
            "req_id": req_id,
            "location": location,
            "team": team or "Engineering",
            "apply_url": apply_url,
            "description": desc,
            "date_posted": date_posted,
            "source_type": "Lever",
        })

    return jobs


def _query_ashby(
    company: dict,
    timeout: int = 10,
    session: Optional[requests.Session] = None,
) -> list[dict]:
    """Query Ashby Job Board public API."""
    http = session or _create_http_session()
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
        resp = http.post(endpoint, json={}, headers=headers, timeout=timeout)
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
        desc = item.get("descriptionPlain") or _strip_html(item.get("descriptionHtml", "")) or title
        date_posted = parse_date_posted(item.get("publishedAt") or item.get("updatedAt"))

        jobs.append({
            "title": title,
            "req_id": req_id,
            "location": location,
            "team": team or "Engineering",
            "apply_url": apply_url,
            "description": desc,
            "date_posted": date_posted,
            "source_type": "Ashby",
        })

    return jobs


def _query_kula(
    company: dict,
    timeout: int = 10,
    session: Optional[requests.Session] = None,
) -> list[dict]:
    """Query Kula ATS careers board (JSON/Next.js payload or HTML requisition links)."""
    http = session or _create_http_session()
    careers_url = company.get("careers_url", "").strip()
    if not careers_url:
        return []

    parsed = urlparse(careers_url)
    segments = [s for s in parsed.path.strip("/").split("/") if s]
    slug = company.get("kula_slug") or (segments[0] if segments else re.sub(r"[^a-z0-9_-]+", "", company.get("name", "").lower()))
    endpoint = company.get("feed_url") or f"https://careers.kula.ai/{slug}"

    try:
        resp = http.get(endpoint, headers={"Accept": "text/html,application/json", "User-Agent": DEFAULT_USER_AGENT}, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("Kula query returned HTTP %s for %s", resp.status_code, company.get("name"))
            return []
    except Exception as exc:
        logger.warning("Kula query failed for %s: %s", company.get("name"), exc)
        return []

    jobs: list[dict] = []
    seen_ids: set[str] = set()
    content_type = (resp.headers.get("Content-Type") or "").lower()

    # 1. Direct JSON response
    if "application/json" in content_type or resp.text.lstrip().startswith(("{", "[")):
        try:
            data = resp.json()
            raw_list = data if isinstance(data, list) else data.get("jobs", data.get("data", []))
            for item in raw_list:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or item.get("name") or "").strip()
                if not title:
                    continue
                req_id = str(item.get("id") or item.get("jobId") or "")
                if req_id and req_id in seen_ids:
                    continue
                if req_id:
                    seen_ids.add(req_id)
                job_slug = item.get("slug") or f"{req_id}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}"
                apply_url = item.get("url") or item.get("apply_url") or f"https://careers.kula.ai/{slug}/{job_slug}"
                location = str(item.get("location") or company.get("location") or "Bengaluru")
                team = str(item.get("department") or item.get("team") or "Engineering")
                desc = _strip_html(str(item.get("description") or "")) or title
                jobs.append({
                    "title": title,
                    "req_id": req_id,
                    "location": location,
                    "team": team,
                    "apply_url": apply_url,
                    "description": desc,
                    "source_type": "Kula",
                })
            if jobs:
                return jobs
        except Exception:
            pass

    # 2. HTML link extraction: /<slug>/<numeric_id>-<title-slug>
    body = resp.text or ""
    link_pattern = re.compile(
        rf'href=["\'](?:https?://careers\.kula\.ai)?/{re.escape(slug)}/(\d+)-([^"\'#?]+)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for req_id, job_slug, inner_html in link_pattern.findall(body):
        if req_id in seen_ids:
            continue
        seen_ids.add(req_id)
        title = _strip_html(inner_html) or job_slug.replace("-", " ").title()
        apply_url = f"https://careers.kula.ai/{slug}/{req_id}-{job_slug}"
        jobs.append({
            "title": title,
            "req_id": req_id,
            "location": company.get("location") or "Bengaluru",
            "team": "Engineering",
            "apply_url": apply_url,
            "description": title,
            "source_type": "Kula",
        })

    return jobs


def _query_freshteam(
    company: dict,
    timeout: int = 10,
    session: Optional[requests.Session] = None,
) -> list[dict]:
    """Query Freshteam public job board (HTML job links or JSON payload)."""
    http = session or _create_http_session()
    careers_url = company.get("careers_url", "").strip()
    if not careers_url:
        return []

    endpoint = company.get("feed_url") or careers_url
    try:
        resp = http.get(endpoint, headers={"Accept": "text/html,application/json", "User-Agent": DEFAULT_USER_AGENT}, timeout=timeout)
        if resp.status_code != 200:
            logger.warning("Freshteam query returned HTTP %s for %s", resp.status_code, company.get("name"))
            return []
    except Exception as exc:
        logger.warning("Freshteam query failed for %s: %s", company.get("name"), exc)
        return []

    jobs: list[dict] = []
    seen_ids: set[str] = set()
    content_type = (resp.headers.get("Content-Type") or "").lower()

    if "application/json" in content_type or resp.text.lstrip().startswith(("{", "[")):
        try:
            data = resp.json()
            raw_list = data if isinstance(data, list) else data.get("jobs", data.get("job_postings", []))
            for item in raw_list:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                if not title:
                    continue
                req_id = str(item.get("id") or item.get("slug") or "")
                if req_id and req_id in seen_ids:
                    continue
                if req_id:
                    seen_ids.add(req_id)
                apply_url = item.get("applicant_apply_link") or item.get("url") or careers_url
                location = str(item.get("branch") or item.get("location") or company.get("location") or "Bangalore")
                team = str(item.get("department") or item.get("team") or "Engineering")
                desc = _strip_html(str(item.get("description") or "")) or title
                jobs.append({
                    "title": title,
                    "req_id": req_id,
                    "location": location,
                    "team": team,
                    "apply_url": apply_url,
                    "description": desc,
                    "source_type": "Freshteam",
                })
            if jobs:
                return jobs
        except Exception:
            pass

    body = resp.text or ""
    link_pattern = re.compile(
        r'href=["\']([^"\']*/jobs/([A-Za-z0-9_-]+)/([^"\'#?]+))["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    for href, req_id, slug_part, inner_html in link_pattern.findall(body):
        if req_id in seen_ids:
            continue
        seen_ids.add(req_id)
        title = _strip_html(inner_html) or slug_part.replace("-", " ").title()
        apply_url = urljoin(endpoint, href)
        jobs.append({
            "title": title,
            "req_id": req_id,
            "location": company.get("location") or "Bangalore",
            "team": "Engineering",
            "apply_url": apply_url,
            "description": title,
            "source_type": "Freshteam",
        })

    return jobs


def query_public_ats_feed(
    company: dict,
    timeout: int = 10,
    candidate: Optional[dict] = None,
    session: Optional[requests.Session] = None,
) -> list[dict]:
    """Query public ATS endpoints (Workday, Greenhouse, Lever, Ashby, Kula, Freshteam) and score jobs."""
    ats_type = (company.get("ats_type") or "").strip().lower()
    careers_url = company.get("careers_url", "").lower()
    http = session or _create_http_session()

    raw_jobs: list[dict] = []

    if ats_type == "workday" or "myworkdayjobs.com" in careers_url:
        raw_jobs = _query_workday(company, timeout=timeout, session=http)
    elif ats_type == "greenhouse" or "greenhouse.io" in careers_url:
        raw_jobs = _query_greenhouse(company, timeout=timeout, session=http)
    elif ats_type == "lever" or "lever.co" in careers_url:
        raw_jobs = _query_lever(company, timeout=timeout, session=http)
    elif ats_type == "ashby" or "ashbyhq.com" in careers_url:
        raw_jobs = _query_ashby(company, timeout=timeout, session=http)
    elif ats_type == "kula" or "careers.kula.ai" in careers_url:
        raw_jobs = _query_kula(company, timeout=timeout, session=http)
    elif ats_type == "freshteam" or ".freshteam.com" in careers_url:
        raw_jobs = _query_freshteam(company, timeout=timeout, session=http)
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
    company_category = company.get("tier") or "Enterprise / OEM"

    standardized: list[dict] = []
    for raw in raw_jobs:
        title = raw.get("title", "")
        req_id = raw.get("req_id", "")

        clean_req = re.sub(r"[^A-Za-z0-9_-]+", "", req_id) if req_id else ""
        if clean_req:
            job_id = f"{company_prefix}-{clean_req}"
        else:
            hashed = hashlib.md5(f"{company_name}_{title}".encode("utf-8")).hexdigest()[:8]
            job_id = f"{company_prefix}-{hashed}"

        score_input = {
            "title": title,
            "description": raw.get("description", ""),
            "location": raw.get("location", ""),
        }
        score_res = score_job(score_input, candidate)

        fit_score = score_res["fit_score"]
        passed_gate = score_res["passed_gate"]
        seniority = infer_seniority(title)

        apply_url = raw.get("apply_url", company.get("careers_url", ""))
        url_type = classify_url_type(apply_url)

        source_label = f"Official ({raw.get('source_type', ats_type.title())})"
        next_action = "Draft tailored resume" if fit_score >= 4 else "Review job description"

        entry = {
            "id": job_id,
            "company": company_name,
            "company_category": company_category,
            "team": raw.get("team", "Systems Engineering"),
            "title": title,
            "location": raw.get("location", "Bangalore"),
            "req_id": req_id or "-",
            "seniority": seniority,
            "fit_score": fit_score,
            "fit_rationale": score_res["fit_rationale"],
            "skills_matched": score_res["skills_matched"],
            "apply_url": apply_url,
            "url_type": url_type,
            "source": source_label,
            "status": "Not Applied",
            "date_posted": raw.get("date_posted") or "",
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
    supported_ats = {"workday", "greenhouse", "lever", "ashby", "kula", "freshteam"}
    session = _create_http_session()
    all_openings: list[dict] = []

    for c in companies:
        name = c.get("name", "")
        if company_filter and company_filter.lower() not in name.lower():
            continue

        ats_type = (c.get("ats_type") or "").strip().lower()
        careers_url = c.get("careers_url", "").lower()

        is_supported = (
            ats_type in supported_ats
            or any(
                s in careers_url
                for s in ("myworkdayjobs.com", "greenhouse.io", "lever.co", "ashbyhq.com", "careers.kula.ai", ".freshteam.com")
            )
            or bool(c.get("feed_url") or c.get("ats_url"))
        )

        if not is_supported:
            continue

        logger.info("Scanning %s (%s)...", name, ats_type or "ATS")
        results = query_public_ats_feed(c, timeout=timeout, candidate=candidate, session=session)
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
    """Append newly discovered passing openings to openings.json and sync to Markdown.

    Enforces 3-tier `url_type` ingestion policy:
    - `direct_requisition`: Allowed.
    - `board_role_anchor`: Allowed only when `board_verified` is True or `page_html`
      verifies both the specific role title and a role-wise application CTA.
    - `generic_portal`: Rejected at ingestion.
    """
    json_file = _resolve_path(json_path)
    md_file = _resolve_path(md_path) if md_path else None

    existing_openings: list[dict] = []
    if json_file.exists():
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if not isinstance(loaded, list):
                    raise ValueError(f"Expected list of openings in {json_file}, got {type(loaded).__name__}")
                existing_openings = loaded
        except Exception as exc:
            logger.error("Failed to load existing openings from %s: %s", json_file, exc)
            raise RuntimeError(f"Corrupted or unreadable openings file at {json_file}: {exc}") from exc

    existing_ids: Set[str] = {str(op.get("id")) for op in existing_openings if op.get("id")}
    existing_urls: Set[str] = {
        str(op.get("apply_url")).strip().rstrip("/")
        for op in existing_openings
        if op.get("apply_url") and op.get("apply_url") != "-"
    }

    newly_added: list[dict] = []
    canonical_keys = [
        "id", "company", "company_category", "team", "title", "location", "req_id",
        "seniority", "fit_score", "fit_rationale", "skills_matched",
        "apply_url", "url_type", "source", "status", "date_posted", "date_discovered",
        "last_updated", "next_action"
    ]

    for job in discovered_jobs:
        passed_gate = job.get("passed_gate")
        if passed_gate is None:
            passed_gate = (job.get("fit_score", 0) >= min_fit_score)
        if not passed_gate:
            continue

        job_id = str(job.get("id", "")).strip()
        job_url = str(job.get("apply_url", "")).strip().rstrip("/")
        title = str(job.get("title", "")).strip()

        if not job_id:
            continue

        # 3-tier URL classification gate
        url_type = job.get("url_type") or classify_url_type(job_url)
        if url_type == "generic_portal":
            logger.info("Rejecting generic_portal URL at ingestion for %s: %s", job_id, job_url)
            continue
        if url_type == "board_role_anchor":
            board_ok = bool(job.get("board_verified"))
            if not board_ok and job.get("page_html"):
                board_ok, _ = verify_board_role_cta(str(job["page_html"]), title)
            if not board_ok:
                logger.info("Rejecting unverified board_role_anchor without role+CTA for %s: %s", job_id, job_url)
                continue

        if job_id in existing_ids:
            logger.debug("Skipping existing opening ID: %s", job_id)
            continue
        # For board_role_anchor, multiple distinct roles share the same #roles URL, so deduplicate by ID
        if url_type != "board_role_anchor" and job_url and job_url in existing_urls:
            logger.debug("Skipping existing opening apply URL: %s", job_url)
            continue

        clean_entry = {k: job.get(k) for k in canonical_keys}
        clean_entry["status"] = clean_entry["status"] or "Not Applied"
        clean_entry["skills_matched"] = clean_entry["skills_matched"] or []
        clean_entry["req_id"] = clean_entry["req_id"] or "-"
        clean_entry["url_type"] = url_type
        clean_entry["company_category"] = clean_entry["company_category"] or "Enterprise / OEM"

        existing_openings.append(clean_entry)
        existing_ids.add(job_id)
        if url_type != "board_role_anchor" and job_url:
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
    parser.add_argument("--queries", action="store_true", help="Print generated Tier 1 Google Dorking queries")
    parser.add_argument("--scan-ats", action="store_true", help="Query configured public ATS endpoints")
    parser.add_argument("--ingest-new", action="store_true", help="Append newly discovered passing roles to openings.json")
    parser.add_argument("--company", help="Filter ATS scan to a specific company name")
    parser.add_argument("--profile", type=Path, default=DEFAULT_CANDIDATE_PATH, help="Path to candidate profile JSON")
    parser.add_argument("--companies-file", type=Path, default=DEFAULT_COMPANIES_PATH, help="Path to target companies JSON")
    parser.add_argument("--openings-file", type=Path, default=DEFAULT_OPENINGS_PATH, help="Path to openings JSON")
    parser.add_argument("--tracker-file", type=Path, default=DEFAULT_TRACKER_PATH, help="Path to Markdown tracker file")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP request timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Simulate scan without writing changes to disk")

    args = parser.parse_args()

    candidate = load_candidate_profile(args.profile)
    candidate_name = candidate.get("name", "Mansi Agrawal")

    if args.queries:
        queries = generate_tier1_dorking_queries(candidate)
        print(f"\n=== Tier 1 Google Dorking Queries ({candidate_name}) ===\n")
        for i, q in enumerate(queries, 1):
            print(f"{i:2d}. {q}")
        print("\nNote: Execute these queries in Google Search / browser under standard human browsing.")
        print(
            f"Safety limits: Max {LINKEDIN_SAFETY_ENVELOPE['max_views_per_day']} views/day; "
            f"pauses of {LINKEDIN_SAFETY_ENVELOPE['pause_min_sec']}–{LINKEDIN_SAFETY_ENVELOPE['pause_max_sec']}s.\n"
        )
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
                f"       Req: {r['req_id']} | Source: {r['source']} | Type: {r.get('url_type')}\n"
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
