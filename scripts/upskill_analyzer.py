#!/usr/bin/env python3
"""Cross-Role Skill Gap & Upskill Analyzer.

Scans `applications/*/analysis.json` across evaluated job openings, tallies
recurring `skill_gaps` and `missing_standards` with `collections.Counter`,
ranks priorities, and generates `reports/upskill_summary.md`.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any

# Ensure repo root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.jd_analyzer import DEFAULT_APPLICATIONS_DIR, DEFAULT_OPENINGS_PATH
except ModuleNotFoundError:
    from jd_analyzer import DEFAULT_APPLICATIONS_DIR, DEFAULT_OPENINGS_PATH  # type: ignore

DEFAULT_UPSKILL_REPORT_PATH = Path("reports/upskill_summary.md")

_TRANSFERABLE_BASELINE: dict[str, str] = {
    "polarion": "IBM DOORS, 3DEXPERIENCE, DESE, ReqHub, DataHub",
    "jama": "IBM DOORS, 3DEXPERIENCE, ReqHub, DataHub",
    "windchill": "3DEXPERIENCE, DESE, digital-thread traceability",
    "teamcenter": "3DEXPERIENCE, DESE, IBM DOORS",
    "capella": "Cameo, MagicDraw, MSOSA, SysML, Boeing Architecture Method",
    "rhapsody": "Cameo, MagicDraw, executable SysML state machines",
    "enterprise architect": "Cameo, MagicDraw, SysML",
    "sysml v2": "SysML v1 (Cameo, MagicDraw, executable ConOps models)",
    "scade": "MATLAB, Simulink, executable SysML models, DO-178C",
    "labview": "MATLAB, Simulink, V&V test planning",
    "do-160": "ARP4754A, ARP4761, DO-178C, DO-254, AS9100",
    "iso 26262": "ARP4754A, ARP4761, failure-condition tracing",
    "mosa": "Logical/functional architecture, interface definition",
    "mil-std-882e": "ARP4761, MIL-STD awareness, failure-condition tracing",
}


def _load_openings_index(openings_path: Path) -> dict[str, dict[str, Any]]:
    """Load `data/openings.json` keyed by ID when available; return empty dict if absent."""
    candidate = Path(openings_path)
    if not candidate.exists() and not candidate.is_absolute():
        repo_candidate = REPO_ROOT / candidate
        if repo_candidate.exists():
            candidate = repo_candidate
    if not candidate.exists():
        return {}
    try:
        records = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(records, list):
        return {}
    return {
        str(rec["id"]): rec
        for rec in records
        if isinstance(rec, dict) and rec.get("id")
    }


def _tally_terms(
    records: list[tuple[str, list[str]]],
) -> list[dict[str, Any]]:
    """Count term frequency across openings using Counter, returning ranked dicts."""
    counts: Counter[str] = Counter()
    canonical_label: dict[str, str] = {}
    openings_by_term: dict[str, list[str]] = defaultdict(list)

    for opening_id, raw_terms in records:
        seen_in_opening: set[str] = set()
        for raw in raw_terms:
            term = str(raw).strip()
            if not term:
                continue
            key = term.casefold()
            if key in seen_in_opening:
                continue
            seen_in_opening.add(key)
            canonical_label.setdefault(key, term)
            counts[key] += 1
            openings_by_term[key].append(opening_id)

    ranked = sorted(
        counts.items(),
        key=lambda item: (-item[1], canonical_label[item[0]].casefold()),
    )
    return [
        {
            "skill": canonical_label[key],
            "count": count,
            "openings": sorted(openings_by_term[key]),
        }
        for key, count in ranked
    ]


def aggregate_skill_gaps(
    applications_dir: Path = DEFAULT_APPLICATIONS_DIR,
    openings_path: Path = DEFAULT_OPENINGS_PATH,
) -> dict[str, Any]:
    """Aggregate recurring skill gaps and missing standards from `applications/*/analysis.json`."""
    apps_root = Path(applications_dir)
    openings_index = _load_openings_index(openings_path)

    if not apps_root.exists():
        return {
            "analyzed_count": 0,
            "total_tracked_openings": len(openings_index),
            "top_gaps": [],
            "top_missing_standards": [],
            "analyzed_openings": [],
            "generated_at": date.today().isoformat(),
        }

    analysis_files = sorted(apps_root.glob("*/analysis.json"))
    gap_records: list[tuple[str, list[str]]] = []
    std_records: list[tuple[str, list[str]]] = []
    analyzed_openings: list[dict[str, Any]] = []

    for analysis_file in analysis_files:
        payload = json.loads(analysis_file.read_text(encoding="utf-8"))
        opening_id = str(payload.get("opening_id") or analysis_file.parent.name).strip()
        tracker_meta = openings_index.get(opening_id, {})

        gaps = [str(g).strip() for g in (payload.get("skill_gaps") or []) if str(g).strip()]
        missing_stds = [
            str(s).strip() for s in (payload.get("missing_standards") or []) if str(s).strip()
        ]

        gap_records.append((opening_id, gaps))
        std_records.append((opening_id, missing_stds))
        analyzed_openings.append(
            {
                "opening_id": opening_id,
                "company": str(payload.get("company") or tracker_meta.get("company") or ""),
                "title": str(payload.get("title") or tracker_meta.get("title") or ""),
                "skill_gaps": gaps,
                "missing_standards": missing_stds,
            }
        )

    top_gaps = _tally_terms(gap_records)
    top_missing_standards = [
        {
            "standard": item["skill"],
            "count": item["count"],
            "openings": item["openings"],
        }
        for item in _tally_terms(std_records)
    ]

    return {
        "analyzed_count": len(analyzed_openings),
        "total_tracked_openings": len(openings_index),
        "top_gaps": top_gaps,
        "top_missing_standards": top_missing_standards,
        "analyzed_openings": analyzed_openings,
        "generated_at": date.today().isoformat(),
    }


def write_upskill_report(
    summary: dict[str, Any],
    output_path: Path = DEFAULT_UPSKILL_REPORT_PATH,
) -> Path:
    """Render a cross-role upskill priority report to Markdown."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    analyzed_count = int(summary.get("analyzed_count", 0))
    total_tracked = int(summary.get("total_tracked_openings", 0))
    top_gaps = list(summary.get("top_gaps") or [])
    top_stds = list(summary.get("top_missing_standards") or [])
    analyzed_openings = list(summary.get("analyzed_openings") or [])
    generated_at = str(summary.get("generated_at") or date.today().isoformat())

    lines: list[str] = [
        "# Cross-Role Upskill & Gap Analysis Summary",
        "",
        f"- **Generated At:** {generated_at}",
        f"- **Analyzed Openings:** {analyzed_count}",
        f"- **Tracked Openings in `openings.json`:** {total_tracked}",
        "",
        "## Top Recurring Skill & Tool Gaps",
    ]

    if top_gaps:
        lines.extend(
            [
                "| Rank | Skill / Tool Gap | Frequency | Affected Openings | Verified Transferable Baseline |",
                "|---:|---|---:|---|---|",
            ]
        )
        for idx, item in enumerate(top_gaps, start=1):
            skill = str(item.get("skill", ""))
            count = int(item.get("count", 0))
            openings_str = ", ".join(f"`{op}`" for op in (item.get("openings") or []))
            baseline = _TRANSFERABLE_BASELINE.get(
                skill.casefold(),
                "Cameo, MagicDraw, IBM DOORS, 3DEXPERIENCE",
            )
            lines.append(f"| {idx} | {skill} | {count} | {openings_str} | {baseline} |")
    else:
        lines.append(
            "- No recurring skill gaps recorded yet. Run `python scripts/jd_analyzer.py --id <OPENING_ID>` on target openings first."
        )

    lines.extend(["", "## Missing Aerospace / Domain Standards"])
    if top_stds:
        lines.extend(
            [
                "| Rank | Standard | Frequency | Affected Openings | Verified Transferable Baseline |",
                "|---:|---|---:|---|---|",
            ]
        )
        for idx, item in enumerate(top_stds, start=1):
            std_name = str(item.get("standard", ""))
            count = int(item.get("count", 0))
            openings_str = ", ".join(f"`{op}`" for op in (item.get("openings") or []))
            baseline = _TRANSFERABLE_BASELINE.get(
                std_name.casefold(),
                "ARP4754A, ARP4761, DO-178C, DO-254, AS9100",
            )
            lines.append(f"| {idx} | {std_name} | {count} | {openings_str} | {baseline} |")
    else:
        lines.append("- None detected across analyzed openings.")

    lines.extend(["", "## Analyzed Roles Covered"])
    if analyzed_openings:
        for role in analyzed_openings:
            op_id = role.get("opening_id", "")
            comp = role.get("company", "") or "Unknown Company"
            title = role.get("title", "") or "Unknown Title"
            gaps = ", ".join(role.get("skill_gaps") or []) or "None"
            lines.append(f"- `{op_id}` — {title} ({comp}) | Gaps: {gaps}")
    else:
        lines.append("- 0 analyzed roles found.")

    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for aggregating cross-role gaps and writing the upskill report."""
    parser = argparse.ArgumentParser(
        description="Aggregate recurring skill gaps across analyzed applications."
    )
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
        "--output",
        type=Path,
        default=DEFAULT_UPSKILL_REPORT_PATH,
        help="Output Markdown path (default: reports/upskill_summary.md)",
    )

    args = parser.parse_args(argv)
    summary = aggregate_skill_gaps(
        applications_dir=args.applications_dir,
        openings_path=args.openings,
    )
    report_path = write_upskill_report(summary, output_path=args.output)
    print(
        f"Analyzed {summary['analyzed_count']} role(s); "
        f"identified {len(summary['top_gaps'])} unique skill gap(s). "
        f"Saved report: {report_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
