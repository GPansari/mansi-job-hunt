#!/usr/bin/env python3
"""Unified Job Hunt Pipeline Orchestrator.

Chains the full end-to-end Mansi Job Hunt workflow with structured logging
and non-zero exit on critical errors:
  1. ATS discovery (`search_engine.py`: scan public ATS feeds & ingest passing roles)
  2. Link verification (`verify_links.py`: 3-tier URL & CTA health audit)
  3. Markdown tracker sync (`sync_tracker.py --to-md`)
  4. Static portal rebuild (`generate_site.py` -> `docs/index.html`)
  5. Digest compilation (`notifier.py`: `--dry-run` default, `--send` opt-in)
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
from typing import Any, Optional

# Ensure repo root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.generate_site import (
    DEFAULT_CANDIDATE_PATH,
    DEFAULT_OPENINGS_PATH,
    DEFAULT_OUTPUT_PATH,
    build_site,
)
from scripts.notifier import (
    DEFAULT_CANDIDATE_NAME,
    DEFAULT_HISTORY_PATH,
    DEFAULT_MIN_FIT_SCORE,
    DEFAULT_PORTAL_URL,
    DEFAULT_RECIPIENT,
    dispatch_email,
    filter_unnotified_roles,
    generate_digest,
    load_sent_history,
)
from scripts.scorer import load_candidate_profile
from scripts.search_engine import (
    DEFAULT_COMPANIES_PATH,
    DEFAULT_TRACKER_PATH,
    ingest_openings,
    scan_all_ats_feeds,
)
from scripts.sync_tracker import sync_json_to_markdown
from scripts.verify_links import verify_all_openings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("run_pipeline")


def run_pipeline(
    openings_path: Path = DEFAULT_OPENINGS_PATH,
    tracker_path: Path = DEFAULT_TRACKER_PATH,
    companies_path: Path = DEFAULT_COMPANIES_PATH,
    candidate_path: Path = DEFAULT_CANDIDATE_PATH,
    site_output_path: Path = DEFAULT_OUTPUT_PATH,
    history_path: Path = DEFAULT_HISTORY_PATH,
    send_email: bool = False,
    skip_discovery: bool = False,
    skip_verify: bool = False,
    company_filter: Optional[str] = None,
    timeout: int = 10,
    verify_delay: float = 0.5,
) -> dict[str, Any]:
    """Execute the full job hunt pipeline and return a structured summary dict."""
    summary: dict[str, Any] = {
        "started_at": datetime.now().isoformat(),
        "discovered_total": 0,
        "ingested_count": 0,
        "link_audit": None,
        "tracker_synced": False,
        "site_rebuilt": False,
        "unnotified_count": 0,
        "email_dispatched": False,
        "dry_run": not send_email,
    }

    candidate = load_candidate_profile(candidate_path)

    # Stage 1: ATS Discovery
    if not skip_discovery:
        logger.info("Stage 1/5: Running public ATS discovery...")
        if not companies_path.exists():
            raise FileNotFoundError(f"Target companies file not found: {companies_path}")
        companies = json.loads(companies_path.read_text(encoding="utf-8"))
        discovered = scan_all_ats_feeds(
            companies,
            candidate=candidate,
            timeout=timeout,
            company_filter=company_filter,
        )
        summary["discovered_total"] = len(discovered)
        newly_added = ingest_openings(
            discovered,
            json_path=openings_path,
            md_path=tracker_path,
        )
        summary["ingested_count"] = len(newly_added)
        logger.info(
            "ATS discovery finished: %d scanned, %d newly ingested.",
            len(discovered),
            len(newly_added),
        )
    else:
        logger.info("Stage 1/5: Skipping ATS discovery (--skip-discovery).")

    # Stage 2: Link Verification
    if not skip_verify:
        logger.info("Stage 2/5: Auditing opening links & board CTAs...")
        link_summary = verify_all_openings(
            openings_path=openings_path,
            save_updates=True,
            delay=verify_delay,
            skip_inactive=True,
        )
        summary["link_audit"] = {
            "total": link_summary.get("total", 0),
            "active": link_summary.get("active", 0),
            "restricted": link_summary.get("restricted", 0),
            "rate_limited": link_summary.get("rate_limited", 0),
            "dead": link_summary.get("dead", 0),
        }
    else:
        logger.info("Stage 2/5: Skipping link verification (--skip-verify).")

    # Stage 3: Sync Markdown Tracker (--to-md)
    logger.info("Stage 3/5: Synchronizing %s -> %s...", openings_path, tracker_path)
    sync_json_to_markdown(openings_path, tracker_path)
    summary["tracker_synced"] = True

    # Stage 4: Rebuild GitHub Pages Portal
    logger.info("Stage 4/5: Rebuilding static portal at %s...", site_output_path)
    build_site(
        openings_path=openings_path,
        candidate_path=candidate_path,
        output_path=site_output_path,
    )
    summary["site_rebuilt"] = True

    # Stage 5: Digest Compilation (dry-run by default; --send opt-in)
    logger.info("Stage 5/5: Compiling weekly digest (dry_run=%s)...", not send_email)
    openings = json.loads(openings_path.read_text(encoding="utf-8"))
    history = load_sent_history(history_path)
    unnotified = filter_unnotified_roles(openings, history, min_fit_score=DEFAULT_MIN_FIT_SCORE)
    summary["unnotified_count"] = len(unnotified)

    if not unnotified:
        logger.info("No new unnotified active roles >= %.1f; skipping email step.", DEFAULT_MIN_FIT_SCORE)
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
        text_body, html_body = generate_digest(
            unnotified,
            candidate_name=DEFAULT_CANDIDATE_NAME,
            date_str=date_str,
            portal_url=DEFAULT_PORTAL_URL,
        )
        subject = f"Weekly Job Hunt Digest - {date_str} ({len(unnotified)} High-Fit Matches)"
        ok = dispatch_email(
            recipient=DEFAULT_RECIPIENT,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            dry_run=not send_email,
            openings=unnotified,
            history_file=history_path,
            date_str=date_str,
        )
        if not ok:
            raise RuntimeError("Email digest dispatch failed.")
        summary["email_dispatched"] = bool(send_email)

    summary["finished_at"] = datetime.now().isoformat()
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run unified Mansi Job Hunt pipeline.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="Preview digest without sending email (default)")
    mode.add_argument("--send", action="store_true", help="Dispatch digest email via Gmail CLI (opt-in)")
    parser.add_argument("--skip-discovery", action="store_true", help="Skip live ATS discovery stage")
    parser.add_argument("--skip-verify", action="store_true", help="Skip live HTTP link verification stage")
    parser.add_argument("--company", help="Optional company filter for ATS discovery")
    parser.add_argument("--openings", type=Path, default=DEFAULT_OPENINGS_PATH, help="Path to openings.json")
    parser.add_argument("--tracker", type=Path, default=DEFAULT_TRACKER_PATH, help="Path to Openings_Tracker.md")
    parser.add_argument("--companies", type=Path, default=DEFAULT_COMPANIES_PATH, help="Path to target_companies.json")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE_PATH, help="Path to candidate.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Path to generated docs/index.html")
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY_PATH, help="Path to sent_history.json")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout in seconds")
    parser.add_argument("--delay", type=float, default=0.5, help="Per-domain link verification delay in seconds")
    args = parser.parse_args(argv)

    try:
        summary = run_pipeline(
            openings_path=args.openings,
            tracker_path=args.tracker,
            companies_path=args.companies,
            candidate_path=args.candidate,
            site_output_path=args.output,
            history_path=args.history,
            send_email=bool(args.send),
            skip_discovery=args.skip_discovery,
            skip_verify=args.skip_verify,
            company_filter=args.company,
            timeout=args.timeout,
            verify_delay=args.delay,
        )
    except Exception as exc:
        logger.error("Pipeline failed with critical error: %s", exc, exc_info=True)
        return 1

    print("\n=== Pipeline Summary ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
