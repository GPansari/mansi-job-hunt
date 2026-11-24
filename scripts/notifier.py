#!/usr/bin/env python3
"""Weekly Digest Generator & Gmail Dispatcher.

Filters high-fit openings, formats plain-text and responsive HTML digests,
archives generated digests, and dispatches via the Gmail CLI while tracking sent history.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import html
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_RECIPIENT = "agrawal.mansi20@gmail.com"
DEFAULT_SENDER_ACCOUNT = "imgauravpansari@gmail.com"
DEFAULT_OPENINGS_PATH = Path("data/openings.json")
DEFAULT_HISTORY_PATH = Path("reports/sent_history.json")
DEFAULT_REPORTS_DIR = Path("reports")
DEFAULT_CANDIDATE_NAME = "Mansi"
DEFAULT_MIN_FIT_SCORE = 3.0
DEFAULT_PORTAL_URL = os.environ.get(
    "JOB_PORTAL_URL",
    "https://gpansari.github.io/mansi-job-hunt/",
)


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert value to float, returning default on failure."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def load_sent_history(history_file: str | Path = DEFAULT_HISTORY_PATH) -> set[str]:
    """Load the set of already-notified role IDs from sent history."""
    path = Path(history_file)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            sent_set = set()
            for item in data:
                if isinstance(item, str):
                    sent_set.add(item)
                elif isinstance(item, dict) and "id" in item:
                    sent_set.add(item["id"])
            return sent_set
        elif isinstance(data, dict):
            if "sent_ids" in data and isinstance(data["sent_ids"], list):
                return set(data["sent_ids"])
            return set(data.keys())
        return set()
    except Exception as e:
        logger.warning("Could not read sent history file %s (%s). Starting fresh.", path, e)
        return set()


def save_sent_history(
    history: set[str] | list[str],
    history_file: str | Path = DEFAULT_HISTORY_PATH,
) -> None:
    """Save the updated set of sent role IDs to sent history."""
    path = Path(history_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_ids = sorted(list(history))
    path.write_text(json.dumps(sorted_ids, indent=2) + "\n", encoding="utf-8")


def filter_unnotified_roles(
    openings: list[dict[str, Any]],
    history: set[str] | list[str] | None = None,
    min_fit_score: float | int = DEFAULT_MIN_FIT_SCORE,
) -> list[dict[str, Any]]:
    """Filter out openings already notified in history or below min_fit_score."""
    history_set = set(history) if history is not None else set()
    unnotified: list[dict[str, Any]] = []

    for role in openings:
        if not isinstance(role, dict):
            continue
        role_id = role.get("id")
        if not role_id or role_id in history_set:
            continue

        raw_score = role.get("fit_score")
        if raw_score is None:
            continue
        try:
            score = float(raw_score)
        except (ValueError, TypeError):
            continue

        if score >= min_fit_score:
            unnotified.append(role)

    # Sort descending by fit score, then by company name (safely guarding None)
    unnotified.sort(
        key=lambda r: (_safe_float(r.get("fit_score"), 0.0), str(r.get("company") or "")),
        reverse=True,
    )
    return unnotified


def generate_digest(
    openings: list[dict[str, Any]],
    candidate_name: str = DEFAULT_CANDIDATE_NAME,
    new_only: bool = True,
    date_str: str | None = None,
    portal_url: str = DEFAULT_PORTAL_URL,
) -> tuple[str, str]:
    """Generate crisp plain-text and mobile-responsive HTML job digest.

    Returns:
        tuple[str, str]: (text_body, html_body)
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    total_count = len(openings)
    fit_5_count = sum(1 for r in openings if _safe_float(r.get("fit_score")) >= 5.0)
    fit_4_count = sum(1 for r in openings if 4.0 <= _safe_float(r.get("fit_score")) < 5.0)
    fit_3_count = sum(1 for r in openings if 3.0 <= _safe_float(r.get("fit_score")) < 4.0)

    # 1. Plain Text Digest
    text_lines = [
        "=" * 80,
        f"WEEKLY EXECUTIVE JOB HUNT DIGEST - {candidate_name.upper()} AGRAWAL",
        f"Date: {date_str} | New High-Fit Matches: {total_count}",
        f"Online Review Portal: {portal_url}",
        "=" * 80,
        "",
    ]

    if total_count == 0:
        text_lines.append("No new matching roles found for this cycle.")
        text_lines.append("All discovered roles are either already notified or below the fit threshold.")
    else:
        text_lines.append(
            f"Summary: {fit_5_count} direct fits (5/5), {fit_4_count} strong fits (4/5), {fit_3_count} moderate fits (3/5)."
        )
        text_lines.append("")

        for idx, role in enumerate(openings, 1):
            title = role.get("title", "Unknown Role")
            company = role.get("company", "Unknown Company")
            location = role.get("location", "Not specified")
            fit = role.get("fit_score", "N/A")
            req_id = role.get("req_id", "N/A")
            seniority = role.get("seniority", "N/A")
            skills = ", ".join(role.get("skills_matched", [])) or "None listed"
            apply_url = role.get("apply_url", "N/A")
            next_action = role.get("next_action", "Review and submit application")
            rationale = role.get("fit_rationale", "")

            text_lines.extend([
                "-" * 80,
                f"[{idx}] {title} @ {company}",
                "-" * 80,
                f"• Fit Score:      {fit}/5",
                f"• Location:       {location}",
                f"• Req ID:         {req_id} | Seniority: {seniority}",
                f"• Matched Skills: {skills}",
            ])
            if rationale:
                text_lines.append(f"• Fit Rationale:  {rationale}")
            text_lines.extend([
                f"• Next Action:    {next_action}",
                f"• Apply URL:      {apply_url}",
                "",
            ])

    text_lines.extend([
        "=" * 80,
        f"Delivered via Mansi Job Hunt Engine | Recipient: {DEFAULT_RECIPIENT}",
        "=" * 80,
    ])
    text_body = "\n".join(text_lines)

    # 2. HTML Digest (Responsive, Email-Client Compatible)
    cards_html = []
    if total_count == 0:
        cards_html.append("""
        <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; text-align: center; color: #64748b;">
            <p style="margin: 0; font-size: 16px;">No new matching roles to report for this cycle.</p>
            <p style="margin: 8px 0 0 0; font-size: 14px;">All active openings have either been sent or do not meet the minimum fit score.</p>
        </div>
        """)
    else:
        for idx, role in enumerate(openings, 1):
            raw_title = role.get("title") or "Unknown Title"
            raw_company = role.get("company") or "Unknown Company"
            raw_location = role.get("location") or "Bangalore"
            raw_req_id = role.get("req_id") or "N/A"
            raw_seniority = role.get("seniority") or ""
            raw_skills = role.get("skills_matched") or []
            raw_apply_url = role.get("apply_url") or "#"
            raw_next_action = role.get("next_action") or "Draft tailored resume"
            raw_rationale = role.get("fit_rationale") or ""

            fit_val = _safe_float(role.get("fit_score"), 0.0)

            # Badge styling based on fit score
            if fit_val >= 5:
                badge_bg = "#dcfce7"
                badge_color = "#15803d"
                badge_border = "#bbf7d0"
                badge_text = f"Fit {fit_val:g}/5 ★ Direct Match"
            elif fit_val >= 4:
                badge_bg = "#dbeafe"
                badge_color = "#1d4ed8"
                badge_border = "#bfdbfe"
                badge_text = f"Fit {fit_val:g}/5 ★ Strong Fit"
            else:
                badge_bg = "#fef3c7"
                badge_color = "#b45309"
                badge_border = "#fde68a"
                badge_text = f"Fit {fit_val:g}/5 ★ Moderate Fit"

            # HTML-escape all dynamic strings to prevent injection
            title = html.escape(str(raw_title), quote=True)
            company = html.escape(str(raw_company), quote=True)
            location = html.escape(str(raw_location), quote=True)
            req_id = html.escape(str(raw_req_id), quote=True)
            seniority = html.escape(str(raw_seniority), quote=True)
            apply_url = html.escape(str(raw_apply_url), quote=True)
            next_action = html.escape(str(raw_next_action), quote=True)
            rationale = html.escape(str(raw_rationale), quote=True)
            badge_text_esc = html.escape(badge_text, quote=True)

            # Skill pill tags
            skill_pills = "".join(
                f'<span style="display:inline-block; background-color:#f1f5f9; color:#334155; border:1px solid #e2e8f0; border-radius:12px; padding:2px 8px; margin:2px 4px 2px 0; font-size:12px; font-weight:500;">{html.escape(str(s), quote=True)}</span>'
                for s in raw_skills
            ) or '<span style="color:#94a3b8; font-size:12px;">None specified</span>'

            card = f"""
            <div style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                    <div style="font-size: 18px; font-weight: 700; color: #0f172a; line-height: 1.3;">
                        {idx}. {title}
                    </div>
                </div>
                <div style="margin-bottom: 12px;">
                    <span style="display: inline-block; background-color: {badge_bg}; color: {badge_color}; border: 1px solid {badge_border}; font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 12px;">
                        {badge_text_esc}
                    </span>
                    <span style="color: #64748b; font-size: 13px; margin-left: 8px;">
                        Req ID: <strong>{req_id}</strong>
                    </span>
                </div>
                <div style="font-size: 14px; color: #334155; margin-bottom: 12px; line-height: 1.5;">
                    <strong style="color: #0f172a;">{company}</strong> &bull; 📍 {location} {f'&bull; {seniority}' if seniority else ''}
                </div>
                {f'<div style="font-size: 13px; color: #475569; margin-bottom: 10px; font-style: italic;">{rationale}</div>' if rationale else ''}
                <div style="margin-bottom: 14px;">
                    <div style="font-size: 12px; font-weight: 600; text-transform: uppercase; color: #64748b; margin-bottom: 4px; letter-spacing: 0.5px;">Skills Matched:</div>
                    <div>{skill_pills}</div>
                </div>
                <div style="background-color: #f8fafc; border-left: 3px solid #3b82f6; padding: 8px 12px; margin-bottom: 16px; border-radius: 0 4px 4px 0;">
                    <span style="font-size: 13px; color: #1e293b;"><strong>Next Action:</strong> {next_action}</span>
                </div>
                <div style="text-align: right;">
                    <a href="{apply_url}" target="_blank" style="display: inline-block; background-color: #2563eb; color: #ffffff; text-decoration: none; font-size: 14px; font-weight: 600; padding: 10px 20px; border-radius: 6px; box-shadow: 0 1px 2px rgba(37,99,235,0.2);">
                        Apply Now &rarr;
                    </a>
                </div>
            </div>
            """
            cards_html.append(card)

    cards_joined = "\n".join(cards_html)

    candidate_esc = html.escape(str(candidate_name), quote=True)
    date_esc = html.escape(str(date_str), quote=True)
    portal_url_esc = html.escape(str(portal_url), quote=True)

    html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weekly Job Hunt Digest | {candidate_esc} Agrawal</title>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background-color: #f1f5f9;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            color: #0f172a;
            -webkit-font-smoothing: antialiased;
        }}
        @media only screen and (max-width: 600px) {{
            .container {{ width: 100% !important; padding: 12px !important; }}
            .header {{ padding: 20px 16px !important; }}
            .stats-table td {{ display: block !important; width: 100% !important; box-sizing: border-box !important; margin-bottom: 8px; }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 24px 0; background-color: #f1f5f9;">
    <div class="container" style="max-width: 680px; margin: 0 auto; padding: 0 16px;">
        <!-- Header Banner -->
        <div class="header" style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); border-radius: 12px; padding: 28px 24px; color: #ffffff; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.5px; color: #38bdf8; margin-bottom: 6px;">
                Aerospace & Systems Engineering
            </div>
            <h1 style="margin: 0 0 8px 0; font-size: 24px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px;">
                Executive Job Hunt Digest
            </h1>
            <p style="margin: 0; font-size: 15px; color: #cbd5e1;">
                Curated for <strong>{candidate_esc} Agrawal</strong> &bull; {date_esc}
            </p>
        </div>

        <!-- Metrics Summary -->
        <table class="stats-table" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 20px; border-collapse: separate; border-spacing: 8px 0;">
            <tr>
                <td width="33%" style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center;">
                    <div style="font-size: 24px; font-weight: 800; color: #0f172a;">{total_count}</div>
                    <div style="font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-top: 2px;">New Matches</div>
                </td>
                <td width="33%" style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center;">
                    <div style="font-size: 24px; font-weight: 800; color: #15803d;">{fit_5_count}</div>
                    <div style="font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-top: 2px;">Direct Fits (5★)</div>
                </td>
                <td width="33%" style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px; text-align: center;">
                    <div style="font-size: 24px; font-weight: 800; color: #1d4ed8;">{fit_4_count}</div>
                    <div style="font-size: 12px; font-weight: 600; color: #64748b; text-transform: uppercase; margin-top: 2px;">Strong Fits (4★)</div>
                </td>
            </tr>
        </table>

        <!-- Live Review Portal Banner -->
        <div style="background-color: #ffffff; border: 1px solid #bfdbfe; border-left: 4px solid #0284c7; border-radius: 8px; padding: 14px 18px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
            <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td valign="middle">
                        <div style="font-size: 14px; font-weight: 700; color: #0369a1;">
                            🌐 Interactive Role Review Portal
                        </div>
                        <div style="font-size: 12px; color: #64748b; margin-top: 2px;">
                            Filter by company, check live application links, and track statuses online.
                        </div>
                    </td>
                    <td align="right" valign="middle" style="white-space: nowrap; padding-left: 12px;">
                        <a href="{portal_url_esc}" target="_blank" style="display: inline-block; background-color: #0284c7; color: #ffffff; text-decoration: none; font-size: 13px; font-weight: 600; padding: 8px 14px; border-radius: 6px;">
                            Open Portal &rarr;
                        </a>
                    </td>
                </tr>
            </table>
        </div>

        <!-- Openings Cards -->
        {cards_joined}

        <!-- Footer -->
        <div style="text-align: center; font-size: 12px; color: #94a3b8; padding: 24px 0;">
            <p style="margin: 0 0 6px 0;">
                Mansi Job Hunt Engine &bull; Autonomous Aerospace Career Pipeline
            </p>
            <p style="margin: 0;">
                Sender: {DEFAULT_SENDER_ACCOUNT} &bull; Recipient: {DEFAULT_RECIPIENT}
            </p>
        </div>
    </div>
</body>
</html>"""

    return text_body, html_body


def archive_digest(
    html_body: str,
    text_body: str | None = None,
    digest_dir: str | Path = DEFAULT_REPORTS_DIR,
    date_str: str | None = None,
) -> Path:
    """Archive copy of generated HTML and plain-text digest to reports/YYYY-MM-DD-digest.html and .txt."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    target_dir = Path(digest_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    digest_file = target_dir / f"{date_str}-digest.html"
    digest_file.write_text(html_body, encoding="utf-8")

    if text_body is not None:
        text_file = target_dir / f"{date_str}-digest.txt"
        text_file.write_text(text_body, encoding="utf-8")

    return digest_file


def dispatch_email(
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
    dry_run: bool = False,
    role_ids: list[str] | set[str] | None = None,
    openings: list[dict[str, Any]] | None = None,
    history_file: str | Path = DEFAULT_HISTORY_PATH,
    digest_dir: str | Path = DEFAULT_REPORTS_DIR,
    sender_account: str = DEFAULT_SENDER_ACCOUNT,
    date_str: str | None = None,
) -> bool:
    """Dispatch the email digest via Gmail CLI or print preview in dry-run mode."""
    if role_ids is None and openings is not None:
        role_ids = [r.get("id") for r in openings if r.get("id")]
    role_id_list = list(role_ids) if role_ids else []

    if dry_run:
        logger.info("[DRY RUN] Dispatching skipped. Summary:")
        logger.info("  To:             %s", recipient)
        logger.info("  Subject:        %s", subject)
        logger.info("  Sender Account: %s", sender_account)
        logger.info("  Role count:     %d", len(role_id_list))
        return True

    # 1. Archive digest copy
    archive_digest(html_body, text_body=text_body, digest_dir=digest_dir, date_str=date_str)

    # 2. Write temp HTML body file for CLI consumption
    html_fd, html_path = tempfile.mkstemp(suffix=".html", prefix="digest_body_")
    try:
        with open(html_fd, "w", encoding="utf-8") as f:
            f.write(html_body)

        cmd = [
            "gmail",
            "mutate",
            "send",
            "--to",
            recipient,
            "--subject",
            subject,
            "--body-file",
            html_path,
            "--html",
        ]

        env = os.environ.copy()
        if sender_account:
            env["AGY_ACCOUNT"] = sender_account

        logger.info("Invoking Gmail CLI: %s", " ".join(cmd))
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            logger.error("Gmail CLI dispatch failed (exit %d): %s", result.returncode, result.stderr)
            return False

        logger.info("Gmail dispatch successful: %s", result.stdout.strip())

        # 3. Update sent history
        if role_id_list:
            history = load_sent_history(history_file)
            history.update(role_id_list)
            save_sent_history(history, history_file)
            logger.info("Updated sent history with %d new roles.", len(role_id_list))

        return True
    except Exception as e:
        logger.error("Unexpected error during email dispatch: %s", e)
        return False
    finally:
        try:
            os.remove(html_path)
        except OSError:
            pass


def main() -> int:
    """CLI Entrypoint for the weekly digest generator."""
    parser = argparse.ArgumentParser(description="Weekly Digest Generator & Gmail Dispatcher")
    parser.add_argument("--dry-run", action="store_true", help="Preview digest without sending")
    parser.add_argument("--send", action="store_true", help="Send digest email via Gmail CLI")
    parser.add_argument("--recipient", default=DEFAULT_RECIPIENT, help=f"Recipient email (default: {DEFAULT_RECIPIENT})")
    parser.add_argument("--min-fit", type=float, default=DEFAULT_MIN_FIT_SCORE, help=f"Min fit score (default: {DEFAULT_MIN_FIT_SCORE})")
    parser.add_argument("--openings", default=str(DEFAULT_OPENINGS_PATH), help=f"Path to openings JSON (default: {DEFAULT_OPENINGS_PATH})")
    parser.add_argument("--history", default=str(DEFAULT_HISTORY_PATH), help=f"Path to history JSON (default: {DEFAULT_HISTORY_PATH})")
    parser.add_argument("--all", action="store_true", help="Include already-sent roles (ignore history)")
    parser.add_argument("--subject", default=None, help="Custom email subject")
    parser.add_argument("--portal-url", default=DEFAULT_PORTAL_URL, help=f"Web URL for role review portal (default: {DEFAULT_PORTAL_URL})")

    args = parser.parse_args()

    # Load openings
    openings_file = Path(args.openings)
    if not openings_file.exists():
        logger.error("Openings file not found: %s", openings_file)
        return 1

    try:
        openings: list[dict[str, Any]] = json.loads(openings_file.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to parse openings JSON: %s", e)
        return 1

    # Load history
    history = set() if args.all else load_sent_history(args.history)
    unnotified = filter_unnotified_roles(openings, history, min_fit_score=args.min_fit)

    if not unnotified:
        print(f"No new roles to notify (0 unnotified roles with fit score >= {args.min_fit}).")
        return 0

    date_str = datetime.now().strftime("%Y-%m-%d")
    text_body, html_body = generate_digest(
        unnotified,
        candidate_name=DEFAULT_CANDIDATE_NAME,
        date_str=date_str,
        portal_url=args.portal_url,
    )
    subject = args.subject or f"Weekly Job Hunt Digest - {date_str} ({len(unnotified)} High-Fit Matches)"

    # Default to dry-run unless --send is explicitly given
    if args.send:
        success = dispatch_email(
            recipient=args.recipient,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            dry_run=False,
            openings=unnotified,
            history_file=args.history,
        )
        if success:
            print(f"Successfully dispatched digest email with {len(unnotified)} roles to {args.recipient}")
            return 0
        else:
            print("Failed to dispatch digest email via Gmail CLI.", file=sys.stderr)
            return 1
    else:
        # Dry-run / preview mode
        print("=== Digest Preview ===")
        print(f"To: {args.recipient}")
        print(f"Subject: {subject}")
        print(f"Unnotified Matches: {len(unnotified)}")
        print()
        print(text_body)
        return 0


if __name__ == "__main__":
    sys.exit(main())
