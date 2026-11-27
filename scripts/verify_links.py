#!/usr/bin/env python3
"""Link Verifier & Health Auditor for Tracked Openings.

Implements 3-tier `url_type` classification and verification:
1. `direct_requisition`: Verified via ATS API (Lever, Ashby, Greenhouse) or HTTP GET +
   soft-404 body checks with per-domain rate limiting (Workday HTTP 429 is recorded as
   `rate_limited` and never misclassified as `expired`).
2. `board_role_anchor`: Startup single-page boards (e.g. `https://www.greenaero.in/careers/#roles`)
   without per-role URLs; verified active only when the page contains BOTH the specific role
   title AND a role-wise application CTA (Apply button, form link, or `mailto:`).
3. `generic_portal`: Bare careers homepages with no specific role or CTA.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import html as html_lib
import json
import logging
from pathlib import Path
import re
import time
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OPENINGS_PATH = Path("data/openings.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SOFT_404_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"job\s+(?:you\s+are\s+looking\s+for\s+)?is\s+no\s+longer\s+available", re.IGNORECASE),
    re.compile(r"this\s+(?:job|position|posting|role)\s+(?:has\s+been\s+filled|is\s+closed|has\s+expired)", re.IGNORECASE),
    re.compile(r"no\s+longer\s+accepting\s+applications", re.IGNORECASE),
    re.compile(r"the\s+page\s+you\s+requested\s+(?:cannot|could\s+not)\s+be\s+found", re.IGNORECASE),
    re.compile(r"job\s+not\s+found", re.IGNORECASE),
    re.compile(r"posting\s+(?:not\s+found|expired|closed)", re.IGNORECASE),
)

CTA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"mailto:[^\s\"'<>]+", re.IGNORECASE),
    re.compile(r"forms\.gle|docs\.google\.com/forms|typeform\.com|airtable\.com/app", re.IGNORECASE),
    re.compile(r"<form\b", re.IGNORECASE),
    re.compile(r"\bapply\s+now\b|\bapply\s+for\s+this\b|\bsubmit\s+application\b|\bapply\s+here\b", re.IGNORECASE),
    re.compile(r"<(?:a|button)\b[^>]*>[^<]*\bapply\b[^<]*</(?:a|button)>", re.IGNORECASE),
)

GENERIC_PORTAL_PATHS = {
    "",
    "careers",
    "en/careers",
    "career",
    "jobs",
    "en/jobs",
    "openings",
    "join-us",
    "work-with-us",
}


def create_http_session() -> requests.Session:
    """Create a requests.Session with conservative retry/backoff (excluding 429)."""
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session


def classify_url_type(url: str) -> str:
    """Classify an opening URL into `direct_requisition`, `board_role_anchor`, or `generic_portal`."""
    raw = (url or "").strip()
    if not raw or raw.startswith("#") or raw.upper() == "N/A":
        return "generic_portal"

    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "generic_portal"

    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    path_lower = path.lower()
    fragment = (parsed.fragment or "").strip().lower()

    # Single-page startup career boards with a roles anchor (e.g. /careers/#roles)
    if fragment and any(tok in fragment for tok in ("role", "opening", "job", "position", "career")):
        return "board_role_anchor"

    # Explicit bare ATS board homepages without a specific requisition slug/ID
    segments = [s for s in path.split("/") if s]
    if host == "careers.kula.ai" and len(segments) <= 1:
        return "generic_portal"
    if host in ("jobs.lever.co", "jobs.ashbyhq.com", "boards.greenhouse.io") and len(segments) <= 1:
        return "generic_portal"
    if host.endswith(".freshteam.com") and path_lower in ("", "jobs"):
        return "generic_portal"
    if "myworkdayjobs.com" in host and "/job/" not in f"/{path_lower}/":
        return "generic_portal"

    # Generic root/careers portals
    if path_lower in GENERIC_PORTAL_PATHS:
        return "generic_portal"

    return "direct_requisition"


def _strip_html_text(body: str) -> str:
    """Strip scripts/styles/tags and decode HTML entities for text matching."""
    cleaned = re.sub(r"<script\b[^>]*>.*?</script>", " ", body, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<style\b[^>]*>.*?</style>", " ", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = html_lib.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def verify_board_role_cta(page_html: str, role_title: str) -> tuple[bool, str]:
    """Verify that a single-page careers board contains BOTH the role title AND an application CTA."""
    if not page_html or not role_title or not role_title.strip():
        return False, "Missing page HTML or role title for board anchor verification"

    plain_text = _strip_html_text(page_html)
    normalized_title = re.sub(r"\s+", " ", role_title).strip()
    has_title = normalized_title.casefold() in plain_text.casefold()
    if not has_title:
        # Try token-level match for punctuation/dash variations
        title_tokens = [t for t in re.findall(r"[A-Za-z0-9]+", normalized_title.casefold()) if len(t) > 2]
        if title_tokens and all(re.search(rf"\b{re.escape(tok)}\b", plain_text.casefold()) for tok in title_tokens):
            has_title = True

    if not has_title:
        return False, f"Role title '{role_title}' not found on careers board page"

    has_cta = any(pattern.search(page_html) for pattern in CTA_PATTERNS)
    if not has_cta:
        return False, f"Role '{role_title}' found, but no application CTA (Apply button, form, or mailto:) detected"

    return True, "Board role title and application CTA verified"


def _check_ats_api_direct(url: str, session: requests.Session, timeout: int) -> dict[str, Any] | None:
    """Attempt fast, authoritative ATS API verification for Lever/Ashby/Greenhouse direct URLs."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    segments = [s for s in parsed.path.strip("/").split("/") if s]

    try:
        if host == "jobs.lever.co" and len(segments) >= 2:
            company_slug, job_id = segments[0], segments[1]
            api_url = f"https://api.lever.co/v0/postings/{company_slug}/{job_id}"
            resp = session.get(api_url, timeout=timeout)
            if resp.status_code == 200:
                return {"status": "active", "http_code": 200, "final_url": url, "reason": "Verified via Lever API", "is_active": True}
            if resp.status_code in (404, 410):
                return {"status": "dead", "http_code": resp.status_code, "final_url": url, "reason": f"Lever API HTTP {resp.status_code}", "is_active": False}
        elif host == "boards.greenhouse.io" and len(segments) >= 3 and segments[1] == "jobs":
            board_token, job_id = segments[0], segments[2]
            api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}"
            resp = session.get(api_url, timeout=timeout)
            if resp.status_code == 200:
                return {"status": "active", "http_code": 200, "final_url": url, "reason": "Verified via Greenhouse API", "is_active": True}
            if resp.status_code in (404, 410):
                return {"status": "dead", "http_code": resp.status_code, "final_url": url, "reason": f"Greenhouse API HTTP {resp.status_code}", "is_active": False}
    except requests.RequestException:
        return None

    return None


def check_url_health(
    url: str,
    timeout: int = 8,
    url_type: str | None = None,
    role_title: str | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Audit a single URL according to its 3-tier `url_type` classification."""
    if not url or url.startswith("#") or url == "N/A":
        return {
            "url_type": "generic_portal",
            "status": "missing",
            "http_code": None,
            "reason": "Missing or placeholder URL",
            "is_active": False,
        }

    resolved_type = url_type or classify_url_type(url)
    if resolved_type == "generic_portal":
        return {
            "url_type": "generic_portal",
            "status": "generic_portal",
            "http_code": None,
            "reason": "Generic careers homepage without specific requisition or role CTA",
            "is_active": False,
        }

    http = session or create_http_session()

    # For direct requisitions on supported ATS, try authoritative API first
    if resolved_type == "direct_requisition":
        ats_res = _check_ats_api_direct(url, http, timeout)
        if ats_res is not None:
            ats_res["url_type"] = resolved_type
            return ats_res

    try:
        resp = http.get(url, timeout=timeout, allow_redirects=True)
        code = resp.status_code
        final_url = resp.url
        body = resp.text or ""
    except requests.RequestException as exc:
        return {
            "url_type": resolved_type,
            "status": "error",
            "http_code": None,
            "reason": f"Connection Error: {exc}",
            "is_active": False,
        }

    if code in (403, 401, 999):
        return {
            "url_type": resolved_type,
            "status": "restricted",
            "http_code": code,
            "final_url": final_url,
            "reason": f"HTTP {code} (Protected portal/anti-bot; valid for human browser)",
            "is_active": True,
        }

    if code == 429:
        # Never mark Workday/ATS HTTP 429 rate-limits as expired!
        return {
            "url_type": resolved_type,
            "status": "rate_limited",
            "http_code": 429,
            "final_url": final_url,
            "reason": "HTTP 429 (ATS rate-limited; not marked expired)",
            "is_active": True,
        }

    if code in (404, 410):
        return {
            "url_type": resolved_type,
            "status": "dead",
            "http_code": code,
            "final_url": final_url,
            "reason": f"HTTP {code} Not Found (Posting likely closed/removed)",
            "is_active": False,
        }

    if code >= 400:
        return {
            "url_type": resolved_type,
            "status": "warning",
            "http_code": code,
            "final_url": final_url,
            "reason": f"HTTP Error {code}",
            "is_active": False,
        }

    # Redirected to expired/not-found page
    if "job-not-found" in final_url.lower() or "expired" in final_url.lower():
        return {
            "url_type": resolved_type,
            "status": "expired",
            "http_code": code,
            "final_url": final_url,
            "reason": "Redirected to job expired/not found page",
            "is_active": False,
        }

    # Board role anchor: verify BOTH role title and application CTA presence
    if resolved_type == "board_role_anchor":
        if role_title:
            ok, reason = verify_board_role_cta(body, role_title)
            return {
                "url_type": resolved_type,
                "status": "active" if ok else "expired",
                "http_code": code,
                "final_url": final_url,
                "reason": reason,
                "is_active": ok,
            }
        # If no role_title supplied, still verify CTA presence
        has_cta = any(pattern.search(body) for pattern in CTA_PATTERNS)
        return {
            "url_type": resolved_type,
            "status": "active" if has_cta else "expired",
            "http_code": code,
            "final_url": final_url,
            "reason": "Board CTA verified" if has_cta else "No application CTA detected on board page",
            "is_active": has_cta,
        }

    # Soft-404 body inspection for direct_requisition
    plain_body = _strip_html_text(body)
    for pattern in SOFT_404_PATTERNS:
        if pattern.search(plain_body):
            return {
                "url_type": resolved_type,
                "status": "expired",
                "http_code": code,
                "final_url": final_url,
                "reason": f"Soft-404 detected in page body ({pattern.pattern})",
                "is_active": False,
            }

    return {
        "url_type": resolved_type,
        "status": "active",
        "http_code": code,
        "final_url": final_url,
        "reason": "OK (Active)",
        "is_active": True,
    }


def verify_all_openings(
    openings_path: Path = DEFAULT_OPENINGS_PATH,
    save_updates: bool = True,
    delay: float = 0.5,
    skip_inactive: bool = False,
) -> dict[str, Any]:
    """Scan openings in the JSON registry with per-domain rate limiting and record link health."""
    if not openings_path.exists():
        logger.error("Openings file not found: %s", openings_path)
        return {"total": 0, "active": 0, "dead": 0, "restricted": 0, "rate_limited": 0}

    data = json.loads(openings_path.read_text(encoding="utf-8"))
    today = datetime.now().strftime("%Y-%m-%d")

    session = create_http_session()
    domain_last_request: dict[str, float] = {}

    results: dict[str, Any] = {
        "total": len(data),
        "active": 0,
        "dead": 0,
        "restricted": 0,
        "rate_limited": 0,
        "details": [],
    }

    print(f"\nAuditing {len(data)} application links in {openings_path}...\n")
    print(f"{'ID':<25} {'Type':<18} {'Status':<13} {'HTTP':<6} {'URL'}")
    print("-" * 92)

    for role in data:
        role_id = role.get("id", "Unknown")
        url = role.get("apply_url", "")
        title = role.get("title", "")
        url_type = role.get("url_type") or classify_url_type(url)
        role["url_type"] = url_type

        if skip_inactive and str(role.get("status") or "").strip().casefold() == "inactive posting":
            continue

        # Per-domain rate limiting
        domain = urlparse(url).netloc.lower()
        if delay and domain and domain in domain_last_request:
            elapsed = time.monotonic() - domain_last_request[domain]
            if elapsed < delay:
                time.sleep(delay - elapsed)

        health = check_url_health(url, url_type=url_type, role_title=title, session=session)
        if domain:
            domain_last_request[domain] = time.monotonic()

        # Preserve status on rate_limited (never mark Workday 429 as expired)
        role["link_status"] = health["status"]
        role["link_http_code"] = health["http_code"]
        role["link_last_checked"] = today

        status_str = health["status"].upper()
        http_code_str = str(health["http_code"]) if health["http_code"] else "ERR"

        if health["status"] == "rate_limited":
            results["rate_limited"] += 1
        elif health["status"] == "restricted":
            results["restricted"] += 1
        elif health["is_active"]:
            results["active"] += 1
        else:
            results["dead"] += 1

        results["details"].append({
            "id": role_id,
            "company": role.get("company"),
            "title": title,
            "url": url,
            "url_type": url_type,
            "health": health,
        })

        print(f"{role_id:<25} {url_type:<18} {status_str:<13} {http_code_str:<6} {url[:40]}...")

    if save_updates:
        openings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        logger.info("Saved link verification metadata into %s", openings_path)

    print("-" * 92)
    print(
        f"Summary: Total: {results['total']} | "
        f"Active/Valid: {results['active']} | "
        f"Protected/Restricted: {results['restricted']} | "
        f"Rate-Limited: {results['rate_limited']} | "
        f"Dead/Expired: {results['dead']}\n"
    )

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit and verify job opening links.")
    parser.add_argument("--path", type=Path, default=DEFAULT_OPENINGS_PATH, help="Path to openings.json")
    parser.add_argument("--no-save", action="store_true", help="Do not write verification status back to JSON")
    parser.add_argument("--delay", type=float, default=0.5, help="Per-domain rate-limit delay in seconds")
    parser.add_argument("--skip-inactive", action="store_true", help="Skip roles already marked Inactive Posting")
    args = parser.parse_args()

    verify_all_openings(
        openings_path=args.path,
        save_updates=not args.no_save,
        delay=args.delay,
        skip_inactive=args.skip_inactive,
    )
