#!/usr/bin/env python3
"""Dual Tracker Synchronization Utility.

Synchronizes job openings between structured JSON (data/openings.json)
and human-readable Markdown (data/Openings_Tracker.md).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

COLUMN_MAP = {
    "company": "company",
    "team": "team",
    "role": "title",
    "title": "title",
    "location": "location",
    "req id": "req_id",
    "req_id": "req_id",
    "seniority": "seniority",
    "fit": "fit_score",
    "fit (1-5)": "fit_score",
    "fit_score": "fit_score",
    "status": "status",
    "link": "apply_url",
    "url": "apply_url",
    "apply_url": "apply_url",
    "next action": "next_action",
    "next_action": "next_action",
}


def escape_table_cell(text: Any) -> str:
    """Escape vertical pipes and newlines for Markdown table cells."""
    if text is None:
        return ""
    s = str(text).replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()
    # Replace unescaped pipes with \|
    s = re.sub(r"(?<!\\)\|", r"\|", s)
    return s


def format_markdown_link(url: str) -> str:
    """Format apply URL as Markdown link."""
    url = (url or "").strip()
    if not url or url == "-":
        return "-"
    if url.startswith("[") and "](" in url:
        return url
    if url.startswith("http://") or url.startswith("https://"):
        return f"[Apply]({url})"
    return url


def extract_url_from_markdown(cell: str) -> str:
    """Extract raw URL from Markdown link cell or return text."""
    cell = (cell or "").strip()
    if not cell or cell == "-":
        return ""
    m = re.search(r"\[.*?\]\((https?://[^\s\)]+)\)", cell)
    if m:
        return m.group(1).strip()
    m_raw = re.search(r"(https?://[^\s\|]+)", cell)
    if m_raw:
        return m_raw.group(1).strip()
    return cell


def parse_fit_score(val: str) -> int:
    """Parse fit score into integer (1-5)."""
    val = (val or "").strip()
    try:
        score = int(float(val))
        return max(1, min(5, score))
    except (ValueError, TypeError):
        return 1


def split_table_row(line: str) -> list[str]:
    """Split a Markdown table row into cells, handling escaped pipes."""
    placeholder = "\x00PIPE\x00"
    cleaned = line.strip()
    if cleaned.startswith("|"):
        cleaned = cleaned[1:]
    if cleaned.endswith("|"):
        cleaned = cleaned[:-1]
    escaped = cleaned.replace(r"\|", placeholder)
    cells = [c.replace(placeholder, "|").strip() for c in escaped.split("|")]
    return cells


def sync_json_to_markdown(json_path: Path, md_path: Path) -> None:
    """Read openings from JSON and generate formatted Markdown tracker."""
    json_path = Path(json_path)
    md_path = Path(md_path)

    if not json_path.exists():
        raise FileNotFoundError(f"Source JSON file not found: {json_path}")

    data: list[dict[str, Any]] = json.loads(json_path.read_text(encoding="utf-8"))

    headers = [
        "Company",
        "Team",
        "Role",
        "Location",
        "Req ID",
        "Seniority",
        "Fit",
        "Status",
        "Link",
        "Next Action",
    ]

    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"

    rows: list[str] = []
    for op in data:
        company = escape_table_cell(op.get("company", ""))
        team = escape_table_cell(op.get("team", ""))
        role = escape_table_cell(op.get("title", ""))
        location = escape_table_cell(op.get("location", ""))
        req_id = escape_table_cell(op.get("req_id", ""))
        seniority = escape_table_cell(op.get("seniority", ""))
        fit = escape_table_cell(str(op.get("fit_score", "")))
        status = escape_table_cell(op.get("status", ""))
        link = format_markdown_link(op.get("apply_url", ""))
        next_action = escape_table_cell(op.get("next_action", ""))

        row_line = (
            f"| {company} | {team} | {role} | {location} | {req_id} | "
            f"{seniority} | {fit} | {status} | {link} | {next_action} |"
        )
        rows.append(row_line)

    table_content = "\n".join([header_line, separator_line] + rows)

    md_text = f"""# Job Openings Tracker

Tracking aerospace & MBSE job openings for Mansi Agrawal's job search.

## Openings Tracker

{table_content}

## Legend — What Each Column Captures

- **Company / Team**: Employer and specific department or project team.
- **Role / Location / Req ID**: Job title, work location, and employer job requisition ID.
- **Seniority**: Target seniority level (Lead, Senior Lead, Manager, etc.).
- **Fit**: Match score (1-5) based on MBSE / Systems Engineering profile.
- **Status**: Not Applied / Applied / Screening / Interview / Offer / Rejected / Watching / Needs Review.
- **Link**: Direct application link or careers portal.
- **Next Action**: Immediate next step for Mansi or agent.
"""
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")


def sync_markdown_to_json(md_path: Path, json_path: Path) -> None:
    """Read openings table from Markdown and update JSON tracker preserving metadata."""
    md_path = Path(md_path)
    json_path = Path(json_path)

    if not md_path.exists():
        raise FileNotFoundError(f"Source Markdown file not found: {md_path}")

    md_lines = md_path.read_text(encoding="utf-8").splitlines()

    # Load existing JSON data if present to preserve metadata
    existing_records: list[dict[str, Any]] = []
    if json_path.exists():
        try:
            existing_records = json.loads(json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing_records = []

    # Build lookup dictionaries
    lookup_by_req: dict[tuple[str, str], dict[str, Any]] = {}
    lookup_by_title: dict[tuple[str, str], dict[str, Any]] = {}
    seen_ids: set[str] = set()

    for item in existing_records:
        item_id = item.get("id", "")
        if item_id:
            seen_ids.add(item_id)
        comp = item.get("company", "").strip().lower()
        req = item.get("req_id", "").strip().lower()
        title = item.get("title", "").strip().lower()
        if comp and req and req not in {"unknown", "n/a", "-", ""}:
            lookup_by_req[(comp, req)] = item
        if comp and title:
            lookup_by_title[(comp, title)] = item

    # Locate table header
    header_indices: dict[str, int] = {}
    in_table = False
    table_rows: list[dict[str, Any]] = []

    for line in md_lines:
        line_str = line.strip()
        if not line_str.startswith("|"):
            if in_table:
                # End of table
                break
            continue

        cells = split_table_row(line_str)
        lower_cells = [c.lower() for c in cells]

        # Check for header
        if not in_table:
            if "company" in lower_cells and ("role" in lower_cells or "fit" in lower_cells):
                for idx, col in enumerate(lower_cells):
                    mapped = COLUMN_MAP.get(col)
                    if mapped:
                        header_indices[mapped] = idx
                in_table = True
                continue

        # Skip separator line
        if all(re.match(r"^:?-+:?$", c) for c in cells if c):
            continue

        # Process row
        if len(cells) < len(header_indices):
            continue

        row_data: dict[str, Any] = {}
        for field, idx in header_indices.items():
            if idx < len(cells):
                row_data[field] = cells[idx]
            else:
                row_data[field] = ""

        # Normalize fields
        company = row_data.get("company", "").strip()
        team = row_data.get("team", "").strip()
        title = row_data.get("title", "").strip()
        location = row_data.get("location", "").strip()
        req_id = row_data.get("req_id", "").strip()
        seniority = row_data.get("seniority", "").strip()
        fit_score = parse_fit_score(row_data.get("fit_score", "1"))
        status = row_data.get("status", "Not Applied").strip()
        apply_url = extract_url_from_markdown(row_data.get("apply_url", ""))
        next_action = row_data.get("next_action", "").strip()

        if not company or not title:
            continue

        comp_key = company.lower()
        req_key = req_id.lower()
        title_key = title.lower()

        # Try to find existing record
        matched: dict[str, Any] | None = None
        if req_key and req_key not in {"unknown", "n/a", "-", ""}:
            matched = lookup_by_req.get((comp_key, req_key))
        if matched is None:
            matched = lookup_by_title.get((comp_key, title_key))

        today_str = datetime.now().strftime("%Y-%m-%d")

        if matched:
            record = dict(matched)
            changed = (
                record.get("company") != company
                or record.get("team") != team
                or record.get("title") != title
                or record.get("location") != location
                or record.get("req_id") != req_id
                or record.get("seniority") != seniority
                or record.get("fit_score") != fit_score
                or record.get("status") != status
                or record.get("apply_url") != apply_url
                or record.get("next_action") != next_action
            )
            record["company"] = company
            record["team"] = team
            record["title"] = title
            record["location"] = location
            record["req_id"] = req_id
            record["seniority"] = seniority
            record["fit_score"] = fit_score
            record["status"] = status
            record["apply_url"] = apply_url
            record["next_action"] = next_action
            if changed:
                record["last_updated"] = today_str
        else:
            # Generate new record
            comp_slug = re.sub(r"[^A-Z0-9]+", "", company.upper())[:10] or "COMPANY"
            req_slug = re.sub(r"[^A-Z0-9]+", "", req_id.upper())[:15]
            if not req_slug or req_slug in {"NA", "UNKNOWN", ""}:
                req_slug = re.sub(r"[^A-Z0-9]+", "", title.upper())[:15]

            base_id = f"{comp_slug}-{req_slug}"
            candidate_id = base_id
            counter = 1
            while candidate_id in seen_ids:
                candidate_id = f"{base_id}-{counter}"
                counter += 1

            record = {
                "id": candidate_id,
                "company": company,
                "team": team,
                "title": title,
                "location": location,
                "req_id": req_id,
                "seniority": seniority,
                "fit_score": fit_score,
                "fit_rationale": "Added via Markdown tracker",
                "skills_matched": [],
                "apply_url": apply_url,
                "source": "Manual Tracker",
                "status": status,
                "date_discovered": today_str,
                "last_updated": today_str,
                "next_action": next_action,
            }
            seen_ids.add(candidate_id)

        table_rows.append(record)

    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(table_rows, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronize openings between JSON and Markdown tracker."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--to-md",
        action="store_true",
        help="Sync openings.json -> Openings_Tracker.md (default)",
    )
    group.add_argument(
        "--to-json",
        action="store_true",
        help="Sync Openings_Tracker.md -> openings.json",
    )
    parser.add_argument(
        "--json-path",
        type=Path,
        default=Path("data/openings.json"),
        help="Path to JSON file (default: data/openings.json)",
    )
    parser.add_argument(
        "--md-path",
        type=Path,
        default=Path("data/Openings_Tracker.md"),
        help="Path to Markdown file (default: data/Openings_Tracker.md)",
    )

    args = parser.parse_args()

    if args.to_json:
        sync_markdown_to_json(args.md_path, args.json_path)
        print(f"Successfully synced {args.md_path} -> {args.json_path}")
    else:
        sync_json_to_markdown(args.json_path, args.md_path)
        print(f"Successfully synced {args.json_path} -> {args.md_path}")

    # Keep web portal in sync
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from scripts.generate_site import build_site
        build_site(openings_path=args.json_path)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(
            "Failed to rebuild web portal after tracker sync: %s", e, exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
