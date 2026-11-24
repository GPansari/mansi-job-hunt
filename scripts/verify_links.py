#!/usr/bin/env python3
"""Link Verifier & Health Auditor for Tracked Openings.

Performs HTTP HEAD/GET probes on application URLs with human-mimicking headers,
identifies active vs dead/expired postings, handles Workday/Lever/Greenhouse patterns,
and records link health metadata into data/openings.json.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.request

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


def check_url_health(url: str, timeout: int = 8) -> dict[str, Any]:
    """Audit a single URL and return health status."""
    if not url or url.startswith("#") or url == "N/A":
        return {
            "status": "missing",
            "http_code": None,
            "reason": "Missing or placeholder URL",
            "is_active": False,
        }

    # Normalize url
    req = urllib.request.Request(url, headers=HEADERS, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            code = response.getcode()
            final_url = response.geturl()

            # Some ATS redirect to a generic home/search page when a job is filled
            is_job_specific = True
            if "job-not-found" in final_url.lower() or "expired" in final_url.lower():
                return {
                    "status": "expired",
                    "http_code": code,
                    "final_url": final_url,
                    "reason": "Redirected to job expired/not found page",
                    "is_active": False,
                }

            return {
                "status": "active",
                "http_code": code,
                "final_url": final_url,
                "reason": "OK (Active)",
                "is_active": True,
            }
    except urllib.error.HTTPError as e:
        # Anti-bot/Cloudflare/LinkedIn often return 403 or 999 to scrapers even when link is live
        # 429 is rate-limiting from Workday/ATS when checked repeatedly
        if e.code in (403, 401, 999):
            return {
                "status": "restricted",
                "http_code": e.code,
                "reason": f"HTTP {e.code} (Protected portal/anti-bot; valid for human browser)",
                "is_active": True,
            }
        elif e.code == 429:
            return {
                "status": "rate_limited",
                "http_code": e.code,
                "reason": "HTTP 429 (ATS Rate-Limited for scrapers; active for human browser)",
                "is_active": True,
            }
        elif e.code in (404, 410):
            return {
                "status": "dead",
                "http_code": e.code,
                "reason": f"HTTP {e.code} Not Found (Posting likely closed/removed)",
                "is_active": False,
            }
        else:
            return {
                "status": "warning",
                "http_code": e.code,
                "reason": f"HTTP Error {e.code}",
                "is_active": False,
            }
    except urllib.error.URLError as e:
        return {
            "status": "error",
            "http_code": None,
            "reason": f"Connection Error: {e.reason}",
            "is_active": False,
        }
    except Exception as e:
        return {
            "status": "error",
            "http_code": None,
            "reason": str(e),
            "is_active": False,
        }


def verify_all_openings(
    openings_path: Path = DEFAULT_OPENINGS_PATH,
    save_updates: bool = True,
    delay: float = 0.5,
) -> dict[str, Any]:
    """Scan all openings in the JSON registry and report link status."""
    if not openings_path.exists():
        logger.error("Openings file not found: %s", openings_path)
        return {"total": 0, "active": 0, "dead": 0, "restricted": 0}

    data = json.loads(openings_path.read_text(encoding="utf-8"))
    today = datetime.now().strftime("%Y-%m-%d")

    results = {
        "total": len(data),
        "active": 0,
        "dead": 0,
        "restricted": 0,
        "details": [],
    }

    print(f"\nAuditing {len(data)} application links in {openings_path}...\n")
    print(f"{'ID':<25} {'Fit':<5} {'Status':<12} {'HTTP':<6} {'URL'}")
    print("-" * 80)

    for role in data:
        role_id = role.get("id", "Unknown")
        fit = role.get("fit_score", 0)
        url = role.get("apply_url", "")

        health = check_url_health(url)

        # Update role metadata
        role["link_status"] = health["status"]
        role["link_http_code"] = health["http_code"]
        role["link_last_checked"] = today

        status_str = health["status"].upper()
        http_code_str = str(health["http_code"]) if health["http_code"] else "ERR"

        if health["is_active"]:
            if health["status"] == "restricted":
                results["restricted"] += 1
            else:
                results["active"] += 1
        else:
            results["dead"] += 1

        results["details"].append({
            "id": role_id,
            "company": role.get("company"),
            "title": role.get("title"),
            "url": url,
            "health": health,
        })

        print(f"{role_id:<25} {fit:<5} {status_str:<12} {http_code_str:<6} {url[:45]}...")
        if delay:
            time.sleep(delay)

    if save_updates:
        openings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        logger.info("Saved link verification metadata into %s", openings_path)

    print("-" * 80)
    print(
        f"Summary: Total: {results['total']} | "
        f"Active/Valid: {results['active']} | "
        f"Protected/Restricted: {results['restricted']} | "
        f"Dead/Expired: {results['dead']}\n"
    )

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit and verify job opening links.")
    parser.add_argument("--path", type=Path, default=DEFAULT_OPENINGS_PATH, help="Path to openings.json")
    parser.add_argument("--no-save", action="store_true", help="Do not write verification status back to JSON")
    parser.add_argument("--delay", type=float, default=0.3, help="Polite delay between requests in seconds")
    args = parser.parse_args()

    verify_all_openings(openings_path=args.path, save_updates=not args.no_save, delay=args.delay)
