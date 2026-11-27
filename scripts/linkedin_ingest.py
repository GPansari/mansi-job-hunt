#!/usr/bin/env python3
"""Browser-Assisted LinkedIn Job Ingestion Engine.

Strictly honors `LINKEDIN_SAFETY_ENVELOPE` and NEVER auto-scrapes LinkedIn via
`requests`, `urllib`, or headless bots. Supports two local human-assisted modes:
1. `--from-json <file>`: Ingests JSON exported by `scripts/linkedin_bookmarklet.js`
   from a user's logged-in Chrome browser.
2. `--cdp-url http://127.0.0.1:9222`: Attaches read-only to an already-open local
   Chrome DevTools Protocol session on localhost, enforcing daily view caps
   (`reports/linkedin_views.json`, cap 40/day) and immediate halt on CAPTCHA / HTTP 999.

Normalizes IDs (`LI-<company>-<job_id>`), deduplicates against existing ATS roles,
saves raw JD text to `applications/<id>/jd_raw.txt`, scores via `scripts/scorer.py`,
and ingests passing roles (`fit_score >= 3`) into `data/openings.json` + Markdown tracker.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
import hashlib
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

# Ensure repo root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests

try:
    from scripts.scorer import load_candidate_profile, score_job
    from scripts.search_engine import (
        DEFAULT_OPENINGS_PATH,
        DEFAULT_TRACKER_PATH,
        LINKEDIN_SAFETY_ENVELOPE,
        _make_company_prefix,
        infer_seniority,
        ingest_openings,
    )
except ModuleNotFoundError:
    from scorer import load_candidate_profile, score_job  # type: ignore
    from search_engine import (  # type: ignore
        DEFAULT_OPENINGS_PATH,
        DEFAULT_TRACKER_PATH,
        LINKEDIN_SAFETY_ENVELOPE,
        _make_company_prefix,
        infer_seniority,
        ingest_openings,
    )

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_VIEWS_PATH = Path("reports/linkedin_views.json")
DEFAULT_APPLICATIONS_DIR = Path("applications")
DAILY_VIEW_CAP = min(40, int(LINKEDIN_SAFETY_ENVELOPE.get("max_views_per_day", 50)))

CAPTCHA_SIGNALS = (
    "captcha",
    "security verification",
    "checkpoint/challenge",
    "authwall",
    "http 999",
    "status 999",
    "unusual activity",
)


class LinkedInSafetyHaltError(RuntimeError):
    """Raised immediately when CAPTCHA, HTTP 999, or daily view cap is encountered."""


def check_safety_signals(text: str = "", http_status: Optional[int] = None) -> None:
    """Halt immediately if HTTP 999 or CAPTCHA/checkpoint text is detected."""
    if http_status == 999:
        raise LinkedInSafetyHaltError("LinkedIn HTTP 999 anti-bot response detected — halting immediately.")
    lower = (text or "").lower()
    for signal in CAPTCHA_SIGNALS:
        if signal in lower:
            raise LinkedInSafetyHaltError(
                f"LinkedIn anti-bot/CAPTCHA signal detected ('{signal}') — halting immediately."
            )


def load_daily_view_counter(
    views_path: Path = DEFAULT_VIEWS_PATH,
    today: Optional[str] = None,
) -> dict[str, Any]:
    """Load persistent daily LinkedIn view counter, resetting on a new calendar day."""
    day = today or date.today().isoformat()
    if views_path.exists():
        try:
            data = json.loads(views_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("date") == day:
                return {
                    "date": day,
                    "count": int(data.get("count", 0)),
                    "cap": int(data.get("cap", DAILY_VIEW_CAP)),
                    "viewed_ids": list(data.get("viewed_ids", [])),
                }
        except Exception as exc:
            logger.warning("Could not parse %s (%s); resetting daily view counter.", views_path, exc)
    return {"date": day, "count": 0, "cap": DAILY_VIEW_CAP, "viewed_ids": []}


def save_daily_view_counter(counter: dict[str, Any], views_path: Path = DEFAULT_VIEWS_PATH) -> None:
    """Persist daily LinkedIn view counter to JSON."""
    views_path.parent.mkdir(parents=True, exist_ok=True)
    views_path.write_text(json.dumps(counter, indent=2) + "\n", encoding="utf-8")


def record_linkedin_view(
    job_id: str,
    views_path: Path = DEFAULT_VIEWS_PATH,
    daily_cap: int = DAILY_VIEW_CAP,
    today: Optional[str] = None,
) -> dict[str, Any]:
    """Increment and enforce the persistent daily LinkedIn view counter."""
    counter = load_daily_view_counter(views_path=views_path, today=today)
    cap = min(daily_cap, DAILY_VIEW_CAP)
    if counter["count"] >= cap:
        raise LinkedInSafetyHaltError(
            f"Daily LinkedIn view cap reached ({counter['count']}/{cap} on {counter['date']}) — halting."
        )
    counter["count"] += 1
    counter["cap"] = cap
    if job_id and job_id not in counter["viewed_ids"]:
        counter["viewed_ids"].append(job_id)
    save_daily_view_counter(counter, views_path=views_path)
    return counter


def extract_linkedin_job_id(url: str = "", explicit_id: str = "") -> str:
    """Extract numeric LinkedIn job ID from explicit field or URL."""
    if explicit_id:
        digits = re.sub(r"[^0-9]", "", str(explicit_id))
        if digits:
            return digits
    raw_url = (url or "").strip()
    if raw_url:
        parsed = urlparse(raw_url)
        qs = parse_qs(parsed.query)
        for key in ("currentJobId", "jobId"):
            if key in qs and qs[key]:
                digits = re.sub(r"[^0-9]", "", qs[key][0])
                if digits:
                    return digits
        m = re.search(r"/jobs/view/(?:[^/?#]*-)?(\d{6,})", parsed.path)
        if m:
            return m.group(1)
        m2 = re.search(r"(\d{8,})", raw_url)
        if m2:
            return m2.group(1)
    return ""


def normalize_linkedin_id(company: str, job_id: str, title: str = "") -> str:
    """Build canonical LinkedIn opening ID `LI-<COMPANY>-<JOB_ID>`."""
    prefix = _make_company_prefix(company)
    clean_id = re.sub(r"[^A-Za-z0-9_-]+", "", str(job_id or ""))
    if not clean_id:
        clean_id = hashlib.md5(f"{company}_{title}".encode("utf-8")).hexdigest()[:8]
    return f"LI-{prefix}-{clean_id}"


def _is_duplicate_of_existing(
    candidate_entry: dict[str, Any],
    existing_openings: list[dict[str, Any]],
) -> bool:
    """Deduplicate LinkedIn role against existing ATS roles by ID, req_id, URL, or company+title."""
    cand_id = str(candidate_entry.get("id") or "").strip().casefold()
    cand_req = str(candidate_entry.get("req_id") or "").strip().casefold()
    cand_url = str(candidate_entry.get("apply_url") or "").strip().rstrip("/").casefold()
    cand_comp = re.sub(r"[^a-z0-9]+", " ", str(candidate_entry.get("company") or "").lower()).strip()
    cand_title = re.sub(r"[^a-z0-9]+", " ", str(candidate_entry.get("title") or "").lower()).strip()

    for op in existing_openings:
        if not isinstance(op, dict):
            continue
        if cand_id and str(op.get("id") or "").strip().casefold() == cand_id:
            return True
        if cand_req and cand_req != "-" and str(op.get("req_id") or "").strip().casefold() == cand_req:
            return True
        if cand_url and str(op.get("apply_url") or "").strip().rstrip("/").casefold() == cand_url:
            return True
        ex_comp = re.sub(r"[^a-z0-9]+", " ", str(op.get("company") or "").lower()).strip()
        ex_title = re.sub(r"[^a-z0-9]+", " ", str(op.get("title") or "").lower()).strip()
        if cand_comp and cand_title and cand_comp == ex_comp and cand_title == ex_title:
            return True
    return False


def _save_raw_jd(opening_id: str, jd_text: str, applications_dir: Path = DEFAULT_APPLICATIONS_DIR) -> Optional[Path]:
    """Save raw JD text to `applications/<id>/jd_raw.txt`."""
    cleaned = (jd_text or "").strip()
    if not cleaned:
        return None
    target_dir = applications_dir / opening_id
    target_dir.mkdir(parents=True, exist_ok=True)
    jd_path = target_dir / "jd_raw.txt"
    jd_path.write_text(cleaned + "\n", encoding="utf-8")
    return jd_path


def load_bookmarklet_json(json_path: Path) -> list[dict[str, Any]]:
    """Load job capture records exported by `scripts/linkedin_bookmarklet.js`."""
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        if isinstance(payload.get("jobs"), list):
            return [j for j in payload["jobs"] if isinstance(j, dict)]
        return [payload]
    if isinstance(payload, list):
        return [j for j in payload if isinstance(j, dict)]
    raise ValueError(f"Unsupported bookmarklet JSON structure in {json_path}")


def capture_from_local_cdp(cdp_url: str = "http://127.0.0.1:9222", timeout: int = 5) -> list[dict[str, Any]]:
    """Inspect open LinkedIn Jobs tabs in a local logged-in Chrome CDP session (localhost only)."""
    parsed = urlparse(cdp_url)
    if parsed.hostname not in ("127.0.0.1", "localhost"):
        raise ValueError(f"CDP URL must be local (127.0.0.1 or localhost), got: {cdp_url}")

    resp = requests.get(f"{cdp_url.rstrip('/')}/json", timeout=timeout)
    resp.raise_for_status()
    targets = resp.json()
    if not isinstance(targets, list):
        return []

    captured: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        url = str(target.get("url") or "")
        title_raw = str(target.get("title") or "")
        if "linkedin.com/jobs" not in url.lower():
            continue
        check_safety_signals(title_raw)
        job_id = extract_linkedin_job_id(url=url)
        # Parse browser tab title like "Senior Avionics Engineer | Sarla Aviation | LinkedIn"
        parts = [p.strip() for p in re.split(r"\s*[|\-]\s*", title_raw) if p.strip() and p.strip().lower() != "linkedin"]
        job_title = parts[0] if parts else title_raw
        company = parts[1] if len(parts) > 1 else "Unknown Company"
        captured.append({
            "title": job_title,
            "company": company,
            "location": "Bengaluru",
            "url": url,
            "job_id": job_id,
            "description": str(target.get("description") or title_raw),
        })
    return captured


def ingest_linkedin_records(
    records: list[dict[str, Any]],
    openings_path: Path = DEFAULT_OPENINGS_PATH,
    tracker_path: Path = DEFAULT_TRACKER_PATH,
    views_path: Path = DEFAULT_VIEWS_PATH,
    applications_dir: Path = DEFAULT_APPLICATIONS_DIR,
    candidate: Optional[dict[str, Any]] = None,
    daily_cap: int = DAILY_VIEW_CAP,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Validate, score, deduplicate, save raw JDs, and ingest LinkedIn job records."""
    if candidate is None:
        candidate = load_candidate_profile()

    existing_openings: list[dict[str, Any]] = []
    if openings_path.exists():
        existing_openings = json.loads(openings_path.read_text(encoding="utf-8"))

    today_str = datetime.now().strftime("%Y-%m-%d")
    candidates_to_ingest: list[dict[str, Any]] = []
    skipped_duplicates: list[str] = []
    skipped_low_fit: list[str] = []
    saved_jds: list[str] = []

    for rec in records:
        if not isinstance(rec, dict):
            continue

        http_status = rec.get("http_status")
        raw_desc = str(rec.get("description") or rec.get("jd_text") or "")
        title = str(rec.get("title") or "").strip()
        company = str(rec.get("company") or "").strip()
        url = str(rec.get("url") or rec.get("apply_url") or "").strip()
        location = str(rec.get("location") or "Bengaluru").strip()

        # Immediate halt on CAPTCHA / HTTP 999
        check_safety_signals(f"{title} {raw_desc} {url}", http_status=http_status)

        job_id = extract_linkedin_job_id(url=url, explicit_id=str(rec.get("job_id") or rec.get("req_id") or ""))
        norm_id = normalize_linkedin_id(company, job_id, title=title)

        # Enforce daily view counter (cap 40/day)
        record_linkedin_view(norm_id, views_path=views_path, daily_cap=daily_cap)

        canonical_url = f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id and "linkedin.com" not in url else url
        if not canonical_url and job_id:
            canonical_url = f"https://www.linkedin.com/jobs/view/{job_id}/"

        score_res = score_job(
            {"title": title, "description": raw_desc, "location": location},
            candidate_profile=candidate,
        )

        entry = {
            "id": norm_id,
            "company": company or "Unknown Company",
            "company_category": rec.get("company_category") or "Enterprise / OEM",
            "team": rec.get("team") or "Systems Engineering",
            "title": title,
            "location": location,
            "req_id": job_id or "-",
            "seniority": infer_seniority(title),
            "fit_score": score_res["fit_score"],
            "fit_rationale": score_res["fit_rationale"],
            "skills_matched": score_res["skills_matched"],
            "apply_url": canonical_url,
            "url_type": "direct_requisition",
            "source": "LinkedIn (Browser-Assisted Capture)",
            "status": "Not Applied",
            "date_discovered": today_str,
            "last_updated": today_str,
            "next_action": "Draft tailored resume" if score_res["fit_score"] >= 4 else "Review job description",
            "passed_gate": score_res["passed_gate"],
        }

        if _is_duplicate_of_existing(entry, existing_openings):
            skipped_duplicates.append(norm_id)
            continue

        if not score_res["passed_gate"]:
            skipped_low_fit.append(norm_id)
            continue

        if not dry_run:
            jd_path = _save_raw_jd(norm_id, raw_desc, applications_dir=applications_dir)
            if jd_path:
                saved_jds.append(str(jd_path))

        candidates_to_ingest.append(entry)

    ingested: list[dict[str, Any]] = []
    if candidates_to_ingest and not dry_run:
        ingested = ingest_openings(
            candidates_to_ingest,
            json_path=openings_path,
            md_path=tracker_path,
        )

    return {
        "processed": len(records),
        "ingested": ingested if not dry_run else candidates_to_ingest,
        "skipped_duplicates": skipped_duplicates,
        "skipped_low_fit": skipped_low_fit,
        "saved_jds": saved_jds,
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Browser-assisted LinkedIn job ingestion (safety-envelope enforced).")
    parser.add_argument("--from-json", type=Path, help="Path to JSON exported by scripts/linkedin_bookmarklet.js")
    parser.add_argument("--cdp-url", help="Optional local Chrome DevTools Protocol URL (e.g. http://127.0.0.1:9222)")
    parser.add_argument("--openings", type=Path, default=DEFAULT_OPENINGS_PATH, help="Path to openings.json")
    parser.add_argument("--tracker", type=Path, default=DEFAULT_TRACKER_PATH, help="Path to Openings_Tracker.md")
    parser.add_argument("--views-file", type=Path, default=DEFAULT_VIEWS_PATH, help="Path to daily views counter JSON")
    parser.add_argument("--applications-dir", type=Path, default=DEFAULT_APPLICATIONS_DIR, help="Applications directory")
    parser.add_argument("--dry-run", action="store_true", help="Score and preview without writing openings or JDs")
    args = parser.parse_args(argv)

    records: list[dict[str, Any]] = []
    if args.from_json:
        records.extend(load_bookmarklet_json(args.from_json))
    if args.cdp_url:
        records.extend(capture_from_local_cdp(args.cdp_url))

    if not records:
        print("No LinkedIn records provided. Pass --from-json <file> or --cdp-url http://127.0.0.1:9222.")
        return 0

    try:
        summary = ingest_linkedin_records(
            records,
            openings_path=args.openings,
            tracker_path=args.tracker,
            views_path=args.views_file,
            applications_dir=args.applications_dir,
            dry_run=args.dry_run,
        )
    except LinkedInSafetyHaltError as exc:
        logger.error("SAFETY HALT: %s", exc)
        return 2

    print(
        f"Processed: {summary['processed']} | "
        f"Ingested: {len(summary['ingested'])} | "
        f"Duplicates skipped: {len(summary['skipped_duplicates'])} | "
        f"Low-fit skipped: {len(summary['skipped_low_fit'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
