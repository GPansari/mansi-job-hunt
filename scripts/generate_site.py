#!/usr/bin/env python3
"""Static Site Generator for Mansi Agrawal's Job Hunt Portal.

Generates a clean, responsive single-page application at docs/index.html.
Features:
- Light theme (B2B SaaS / clean enterprise aesthetic)
- Discovered date column + sort options (Newest First, Fit + Recency, Fit Score, Company)
- `url_type` badge (Direct ATS vs Career Board Role)
- Non-overlapping sticky toolbar, sticky table headers, and collapsible mobile filter drawer
- Dynamic `companyFilter` and Candidate Profile drawer populated from JSON
- Accurate `kpi-active` and `kpi-actionable` counts (excluding inactive/dead/expired roles)
- Strict HTML escaping (`escapeHtml`) for every interpolated JS field
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OPENINGS_PATH = Path("data/openings.json")
DEFAULT_CANDIDATE_PATH = Path("profile/candidate.json")
DEFAULT_OUTPUT_PATH = Path("docs/index.html")


def _safe_json_for_script(data: Any) -> str:
    """Serialize JSON safely for inline <script> blocks (preventing </script> breakout)."""
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _is_role_active(role: dict[str, Any]) -> bool:
    """Return True if a role is active (not Inactive Posting and link not dead/expired)."""
    status = str(role.get("status") or "").strip().casefold()
    if status == "inactive posting":
        return False
    link_status = str(role.get("link_status") or "").strip().casefold()
    if link_status in ("dead", "expired"):
        return False
    return True


def build_site(
    openings_path: Path = DEFAULT_OPENINGS_PATH,
    candidate_path: Path = DEFAULT_CANDIDATE_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path:
    """Build the single-page HTML application."""
    if not openings_path.exists():
        raise FileNotFoundError(f"Openings file not found: {openings_path}")

    openings: list[dict[str, Any]] = json.loads(openings_path.read_text(encoding="utf-8"))
    candidate: dict[str, Any] = {}
    if candidate_path.exists():
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))

    # Normalize company_category and url_type if missing
    for r in openings:
        if not r.get("company_category"):
            comp = (r.get("company") or "").lower()
            if any(
                s in comp
                for s in ("sarla", "ideaforge", "digantara", "galaxeye", "reorbit", "newspace", "green aero", "airbound")
            ):
                r["company_category"] = "Startup / Emerging"
            else:
                r["company_category"] = "Enterprise / OEM"
        if not r.get("url_type"):
            url_str = str(r.get("apply_url") or "")
            r["url_type"] = "board_role_anchor" if "#roles" in url_str.lower() else "direct_requisition"

    total_count = len(openings)
    fit_5_count = sum(1 for r in openings if float(r.get("fit_score", 0) or 0) >= 5)
    fit_4_count = sum(1 for r in openings if 4 <= float(r.get("fit_score", 0) or 0) < 5)
    active_count = sum(1 for r in openings if _is_role_active(r))
    actionable_count = sum(
        1
        for r in openings
        if _is_role_active(r) and str(r.get("status") or "Not Applied") in ("Not Applied", "Needs Review")
    )

    openings_json_str = _safe_json_for_script(openings)
    candidate_json_str = _safe_json_for_script(candidate)
    generated_at = datetime.now().strftime("%B %d, %Y")

    candidate_name = str(candidate.get("name") or "Mansi Agrawal")
    candidate_title = str(candidate.get("current_title") or "Lead Systems Engineer")
    candidate_edu = str(candidate.get("education") or "MS Aerospace Engineering, Georgia Tech")
    candidate_exp = candidate.get("experience_years", 10)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{candidate_name} &bull; Aerospace &amp; MBSE Career Portal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-page: #f8fafc;
      --bg-surface: #ffffff;
      --border-subtle: #e2e8f0;
      --border-medium: #cbd5e1;
      --border-focus: #0284c7;
      --text-primary: #0f172a;
      --text-secondary: #475569;
      --text-muted: #64748b;
      --brand-primary: #0284c7;
      --brand-hover: #0369a1;
      --tag-bg: #f1f5f9;
      --tag-text: #334155;
      --green-bg: #ecfdf5;
      --green-text: #047857;
      --green-border: #a7f3d0;
      --blue-bg: #eff6ff;
      --blue-text: #1d4ed8;
      --blue-border: #bfdbfe;
      --amber-bg: #fffbeb;
      --amber-text: #b45309;
      --amber-border: #fde68a;
      --red-bg: #fef2f2;
      --red-text: #b91c1c;
      --red-border: #fecaca;
      --purple-bg: #f5f3ff;
      --purple-text: #6d28d9;
      --purple-border: #ddd6fe;
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
      --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background-color: var(--bg-page);
      color: var(--text-primary);
      min-height: 100vh;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
    }}

    /* Top Navigation Bar — natural flow (no double-sticky overlap with toolbar) */
    header {{
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      padding: 12px 24px;
      position: relative;
      z-index: 20;
      box-shadow: var(--shadow-sm);
    }}
    .header-inner {{
      max-width: 1440px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .brand-title {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .brand-badge {{
      background: #0284c7;
      color: #ffffff;
      padding: 6px 10px;
      border-radius: 8px;
      font-weight: 700;
      font-size: 13px;
      letter-spacing: 0.5px;
    }}
    .brand-title h1 {{
      font-size: 18px;
      font-weight: 800;
      color: var(--text-primary);
      letter-spacing: -0.3px;
    }}
    .brand-title p {{
      font-size: 13px;
      color: var(--text-muted);
    }}
    .header-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 600;
      padding: 7px 12px;
      border-radius: 6px;
      border: 1px solid transparent;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.15s ease;
    }}
    .btn-default {{
      background: var(--bg-surface);
      border-color: var(--border-medium);
      color: var(--text-secondary);
    }}
    .btn-default:hover {{
      background: #f1f5f9;
      color: var(--text-primary);
    }}

    /* Main Container */
    main {{
      max-width: 1440px;
      margin: 18px auto 40px auto;
      padding: 0 24px;
    }}

    /* KPI Summary Row */
    .kpi-row {{
      display: flex;
      align-items: center;
      gap: 16px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 12px 20px;
      margin-bottom: 14px;
      box-shadow: var(--shadow-sm);
      flex-wrap: wrap;
    }}
    .kpi-item {{
      display: flex;
      align-items: baseline;
      gap: 6px;
    }}
    .kpi-val {{
      font-size: 18px;
      font-weight: 800;
      font-family: 'JetBrains Mono', monospace;
      color: var(--text-primary);
    }}
    .kpi-label {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .kpi-sep {{
      color: var(--border-medium);
      font-weight: 300;
    }}

    /* Single Sticky Toolbar */
    .toolbar-container {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 10px 14px;
      margin-bottom: 14px;
      box-shadow: var(--shadow-md);
      position: sticky;
      top: 0;
      z-index: 40;
    }}
    .toolbar-top-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .search-box {{
      position: relative;
      flex: 1;
      min-width: 220px;
      max-width: 360px;
    }}
    .search-box svg {{
      position: absolute;
      left: 10px;
      top: 50%;
      transform: translateY(-50%);
      width: 15px;
      height: 15px;
      color: var(--text-muted);
    }}
    .search-input {{
      width: 100%;
      padding: 7px 12px 7px 32px;
      border-radius: 6px;
      border: 1px solid var(--border-medium);
      font-size: 13px;
      background: #f8fafc;
      color: var(--text-primary);
    }}
    .search-input:focus {{
      outline: none;
      border-color: var(--border-focus);
      background: #ffffff;
      box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.12);
    }}
    .filters-drawer {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }}
    .mobile-filter-toggle {{
      display: none;
    }}
    .select-filter {{
      padding: 6px 10px;
      border-radius: 6px;
      border: 1px solid var(--border-medium);
      font-size: 12px;
      font-weight: 500;
      background: #ffffff;
      color: var(--text-primary);
      cursor: pointer;
    }}
    .active-toggle {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 600;
      padding: 6px 10px;
      background: var(--green-bg);
      border: 1px solid var(--green-border);
      color: var(--green-text);
      border-radius: 6px;
      cursor: pointer;
      user-select: none;
    }}
    .active-toggle input {{
      cursor: pointer;
      accent-color: #059669;
    }}
    .view-switcher {{
      display: inline-flex;
      background: #f1f5f9;
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 2px;
    }}
    .view-btn {{
      padding: 5px 10px;
      border-radius: 4px;
      border: none;
      background: transparent;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .view-btn.active {{
      background: #ffffff;
      color: var(--brand-primary);
      box-shadow: var(--shadow-sm);
    }}

    /* Filter Tag Pills */
    .active-filters-bar {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 12px;
      flex-wrap: wrap;
    }}
    .active-tag {{
      background: #e0f2fe;
      color: #0369a1;
      padding: 2px 8px;
      border-radius: 4px;
      font-weight: 600;
    }}

    /* Tabular List View with Sticky Table Headers */
    .table-container {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      overflow: auto;
      max-height: 75vh;
      box-shadow: var(--shadow-sm);
    }}
    table.jobs-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      text-align: left;
      font-size: 13px;
    }}
    table.jobs-table thead th {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: #f8fafc;
      color: var(--text-muted);
      font-weight: 600;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      padding: 11px 14px;
      border-bottom: 1px solid var(--border-subtle);
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }}
    table.jobs-table thead th:hover {{
      color: var(--text-primary);
    }}
    table.jobs-table td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-subtle);
      vertical-align: middle;
    }}
    table.jobs-table tr.job-row:hover {{
      background: #f8fafc;
    }}
    .role-cell {{
      font-weight: 700;
      color: var(--text-primary);
      font-size: 14px;
      display: block;
    }}
    .company-cell {{
      font-size: 12px;
      color: var(--text-secondary);
      font-weight: 500;
      margin-top: 2px;
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .category-chip {{
      font-size: 10px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 4px;
      text-transform: uppercase;
    }}
    .cat-enterprise {{ background: #e2e8f0; color: #334155; }}
    .cat-startup {{ background: #fef3c7; color: #92400e; }}

    .url-type-badge {{
      display: inline-flex;
      align-items: center;
      font-size: 10px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 4px;
      white-space: nowrap;
    }}
    .url-type-direct {{ background: var(--blue-bg); color: var(--blue-text); border: 1px solid var(--blue-border); }}
    .url-type-board {{ background: var(--purple-bg); color: var(--purple-text); border: 1px solid var(--purple-border); }}

    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 6px;
      white-space: nowrap;
    }}
    .badge-5 {{ background: var(--green-bg); color: var(--green-text); border: 1px solid var(--green-border); }}
    .badge-4 {{ background: var(--blue-bg); color: var(--blue-text); border: 1px solid var(--blue-border); }}
    .badge-3 {{ background: var(--amber-bg); color: var(--amber-text); border: 1px solid var(--amber-border); }}

    .link-pill {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 4px;
      white-space: nowrap;
    }}
    .link-pill-active {{ background: var(--green-bg); color: var(--green-text); }}
    .link-pill-restricted {{ background: #eff6ff; color: #1e40af; }}
    .link-pill-dead {{ background: var(--red-bg); color: var(--red-text); }}

    .skill-chip {{
      display: inline-block;
      background: var(--tag-bg);
      color: var(--tag-text);
      font-size: 11px;
      font-weight: 500;
      padding: 2px 6px;
      border-radius: 4px;
      margin: 1px 3px 1px 0;
      font-family: 'JetBrains Mono', monospace;
    }}
    .date-mono {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      color: var(--text-secondary);
      white-space: nowrap;
    }}
    .status-select-sm {{
      padding: 5px 8px;
      border-radius: 6px;
      border: 1px solid var(--border-medium);
      font-size: 12px;
      background: #ffffff;
      color: var(--text-primary);
      cursor: pointer;
    }}
    .btn-apply-sm {{
      background: var(--brand-primary);
      color: #ffffff;
      text-decoration: none;
      font-size: 12px;
      font-weight: 600;
      padding: 6px 12px;
      border-radius: 6px;
      white-space: nowrap;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .btn-apply-sm:hover {{ background: var(--brand-hover); }}

    .details-row {{ background: #fafafa; display: none; }}
    .details-row.open {{ display: table-row; }}
    .details-content {{
      padding: 12px 18px;
      font-size: 13px;
      color: var(--text-secondary);
      border-left: 3px solid var(--brand-primary);
      margin: 6px 12px;
      background: #ffffff;
      border-radius: 0 6px 6px 0;
      box-shadow: var(--shadow-sm);
    }}

    /* Cards View */
    .cards-grid {{
      display: none;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 16px;
    }}
    .cards-grid.active {{ display: grid; }}
    .job-card {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: var(--shadow-sm);
    }}
    .card-top {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 8px;
      gap: 8px;
    }}
    .card-footer {{
      border-top: 1px solid var(--border-subtle);
      padding-top: 10px;
      margin-top: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }}

    /* Candidate Profile Drawer */
    .drawer-overlay {{
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(15, 23, 42, 0.4);
      z-index: 99;
    }}
    .drawer {{
      position: fixed;
      top: 0; right: -450px; width: 420px; max-width: 90vw; height: 100vh;
      background: #ffffff;
      box-shadow: -4px 0 24px rgba(0,0,0,0.12);
      z-index: 100;
      transition: right 0.25s ease;
      padding: 24px;
      overflow-y: auto;
    }}
    .drawer.open {{ right: 0; }}
    .drawer-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--border-subtle);
      padding-bottom: 12px;
    }}
    .drawer-title {{ font-size: 16px; font-weight: 700; color: var(--text-primary); }}
    .close-btn {{ background: none; border: none; font-size: 20px; cursor: pointer; color: var(--text-muted); }}

    /* Responsive Mobile Collapsible Filter Drawer */
    @media (max-width: 900px) {{
      header {{ padding: 12px 14px; }}
      main {{ padding: 0 12px; margin-top: 12px; }}
      .kpi-sep {{ display: none; }}
      .kpi-item {{ flex: 1 1 42%; }}
      .mobile-filter-toggle {{ display: inline-flex; }}
      .filters-drawer {{
        display: none;
        flex-direction: column;
        align-items: stretch;
        padding-top: 8px;
        border-top: 1px solid var(--border-subtle);
      }}
      .filters-drawer.mobile-open {{
        display: flex;
      }}
      .select-filter {{ width: 100%; }}
      .table-container {{ max-height: 68vh; }}
    }}
  </style>
</head>
<body>

  <header>
    <div class="header-inner">
      <div class="brand-title">
        <div class="brand-badge">AEROSPACE</div>
        <div>
          <h1 id="headerCandidateName">{candidate_name} &bull; Job Hunt Engine</h1>
          <p id="headerCandidateMeta">{candidate_exp}+ Yrs Systems Engineering &bull; {candidate_title} &bull; {candidate_edu}</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="btn btn-default" onclick="toggleDrawer()">
          Candidate Profile
        </button>
      </div>
    </div>
  </header>

  <main>
    <div class="kpi-row">
      <div class="kpi-item">
        <span class="kpi-val" id="kpi-total">{total_count}</span>
        <span class="kpi-label">Total Tracked</span>
      </div>
      <span class="kpi-sep">|</span>
      <div class="kpi-item">
        <span class="kpi-val" style="color: #047857;">{fit_5_count}</span>
        <span class="kpi-label">5★ Direct Fits</span>
      </div>
      <span class="kpi-sep">|</span>
      <div class="kpi-item">
        <span class="kpi-val" style="color: #1d4ed8;">{fit_4_count}</span>
        <span class="kpi-label">4★ Strong Fits</span>
      </div>
      <span class="kpi-sep">|</span>
      <div class="kpi-item">
        <span class="kpi-val" style="color: #0284c7;" id="kpi-active">{active_count}</span>
        <span class="kpi-label">Active Openings</span>
      </div>
      <span class="kpi-sep">|</span>
      <div class="kpi-item">
        <span class="kpi-val" style="color: #6366f1;" id="kpi-actionable">{actionable_count}</span>
        <span class="kpi-label">Actionable (Not Applied)</span>
      </div>
      <div style="margin-left: auto; font-size: 12px; color: var(--text-muted);">
        Synced: <strong>{generated_at}</strong>
      </div>
    </div>

    <div class="toolbar-container">
      <div class="toolbar-top-row">
        <div class="search-box">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
          <input type="text" id="searchInput" class="search-input" placeholder="Search title, company, req ID, skill..." oninput="applyFilters()">
        </div>

        <div style="display:flex; align-items:center; gap:8px;">
          <button id="mobileFilterBtn" class="btn btn-default mobile-filter-toggle" onclick="toggleMobileFilters()">
            Filters
          </button>
          <div class="view-switcher">
            <button id="viewBtnTable" class="view-btn active" onclick="setView('table')">Table</button>
            <button id="viewBtnCards" class="view-btn" onclick="setView('cards')">Cards</button>
          </div>
        </div>
      </div>

      <div id="filtersDrawer" class="filters-drawer">
        <select id="sortSelect" class="select-filter" onchange="applyFilters()" aria-label="Sort openings">
          <option value="fit_recency">Sort: Fit + Recency</option>
          <option value="newest">Sort: Newest First</option>
          <option value="fit_score">Sort: Fit Score</option>
          <option value="company">Sort: Company</option>
        </select>

        <select id="fitFilter" class="select-filter" onchange="applyFilters()">
          <option value="all">Fit: All Scores</option>
          <option value="5">5★ Direct Fits</option>
          <option value="4">4★ Strong Fits</option>
          <option value="3">3★ Moderate Matches</option>
        </select>

        <select id="categoryFilter" class="select-filter" onchange="applyFilters()">
          <option value="all">Category: All</option>
          <option value="Enterprise / OEM">Enterprise / OEM</option>
          <option value="Startup / Emerging">Startup / Emerging</option>
        </select>

        <select id="companyFilter" class="select-filter" onchange="applyFilters()">
          <option value="all">Company: All</option>
        </select>

        <select id="statusFilter" class="select-filter" onchange="applyFilters()">
          <option value="all">Status: All</option>
          <option value="Not Applied">Not Applied</option>
          <option value="Applied">Applied</option>
          <option value="Interviewing">Interviewing</option>
          <option value="Needs Review">Needs Review</option>
          <option value="Watching">Watching</option>
        </select>

        <label class="active-toggle" title="Hide inactive, closed, or expired postings">
          <input type="checkbox" id="activeOnlyToggle" checked onchange="applyFilters()">
          <span>Active Jobs Only</span>
        </label>
      </div>
    </div>

    <div class="active-filters-bar">
      <span>Showing <strong id="matching-count">0</strong> matching roles</span>
      <span id="active-tag-container" style="display: inline-flex; gap: 6px; flex-wrap: wrap;"></span>
    </div>

    <div id="tableView" class="table-container">
      <table class="jobs-table">
        <thead>
          <tr>
            <th onclick="setSort('fit_score')" style="width: 110px;">Fit Score</th>
            <th onclick="setSort('company')">Role &amp; Company</th>
            <th>Location &amp; Team</th>
            <th onclick="setSort('newest')">Discovered</th>
            <th>Matched Skills</th>
            <th>Link &amp; Source</th>
            <th>Status</th>
            <th style="text-align: right;">Action</th>
          </tr>
        </thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>

    <div id="cardsView" class="cards-grid"></div>
  </main>

  <div id="drawerOverlay" class="drawer-overlay" onclick="toggleDrawer()"></div>
  <aside id="candidateDrawer" class="drawer">
    <div class="drawer-header">
      <h3 class="drawer-title" id="drawerCandidateTitle">Candidate Reference</h3>
      <button class="close-btn" onclick="toggleDrawer()">&times;</button>
    </div>
    <div id="candidateDrawerBody" style="font-size: 13px; color: var(--text-secondary); display: flex; flex-direction: column; gap: 16px;"></div>
  </aside>

  <script>
    const OPENINGS = {openings_json_str};
    const CANDIDATE = {candidate_json_str};
    let currentView = 'table';

    function escapeHtml(value) {{
      if (value === null || value === undefined) return '';
      return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }}

    function safeUrl(url) {{
      const raw = String(url || '').trim();
      if (/^https?:\\/\\//i.test(raw)) return escapeHtml(raw);
      return '#';
    }}

    function isRoleActive(r) {{
      const st = String(r.status || '').trim().toLowerCase();
      if (st === 'inactive posting') return false;
      const ls = String(r.link_status || '').trim().toLowerCase();
      if (ls === 'dead' || ls === 'expired') return false;
      return true;
    }}

    function updateKpis() {{
      let active = 0;
      let actionable = 0;
      OPENINGS.forEach(r => {{
        if (isRoleActive(r)) {{
          active++;
          const s = r.status || 'Not Applied';
          if (s === 'Not Applied' || s === 'Needs Review') {{
            actionable++;
          }}
        }}
      }});
      const activeEl = document.getElementById('kpi-active');
      const actionEl = document.getElementById('kpi-actionable');
      if (activeEl) activeEl.textContent = active;
      if (actionEl) actionEl.textContent = actionable;
    }}

    function populateCompanyFilter() {{
      const select = document.getElementById('companyFilter');
      if (!select) return;
      const companies = Array.from(new Set(OPENINGS.map(r => (r.company || '').trim()).filter(Boolean)))
        .sort((a, b) => a.localeCompare(b));
      select.innerHTML = '<option value="all">Company: All</option>' +
        companies.map(c => `<option value="${{escapeHtml(c)}}">${{escapeHtml(c)}}</option>`).join('');
    }}

    function renderCandidateDrawer() {{
      const titleEl = document.getElementById('drawerCandidateTitle');
      const bodyEl = document.getElementById('candidateDrawerBody');
      if (!bodyEl) return;
      const name = CANDIDATE.name || 'Mansi Agrawal';
      if (titleEl) titleEl.textContent = name + ' \u2022 Candidate Reference';

      const skills = Array.isArray(CANDIDATE.core_skills) ? CANDIDATE.core_skills : [];
      const titles = Array.isArray(CANDIDATE.target_titles) ? CANDIDATE.target_titles : [];
      const domains = Array.isArray(CANDIDATE.target_domains) ? CANDIDATE.target_domains : [];

      bodyEl.innerHTML = `
        <div>
          <strong style="color: var(--text-primary); display: block; margin-bottom: 4px;">Profile &amp; Experience</strong>
          <p><strong>Current:</strong> ${{escapeHtml(CANDIDATE.current_title || 'Lead Systems Engineer')}}</p>
          <p><strong>Experience:</strong> ${{escapeHtml(CANDIDATE.experience_years || 10)}}+ Years</p>
          <p><strong>Education:</strong> ${{escapeHtml(CANDIDATE.education || 'MS Aerospace Engineering, Georgia Tech')}}</p>
          <p><strong>Location:</strong> ${{escapeHtml(CANDIDATE.location || 'Bangalore, India')}}</p>
        </div>
        ${{CANDIDATE.summary ? `<div><strong style="color: var(--text-primary); display: block; margin-bottom: 4px;">Summary</strong><p>${{escapeHtml(CANDIDATE.summary)}}</p></div>` : ''}}
        <div>
          <strong style="color: var(--text-primary); display: block; margin-bottom: 6px;">Core Competencies</strong>
          <div style="display: flex; flex-wrap: wrap; gap: 4px;">
            ${{skills.map(s => `<span class="skill-chip">${{escapeHtml(s)}}</span>`).join('')}}
          </div>
        </div>
        <div>
          <strong style="color: var(--text-primary); display: block; margin-bottom: 4px;">Target Titles</strong>
          <p>${{escapeHtml(titles.join(' \u2022 '))}}</p>
        </div>
        <div>
          <strong style="color: var(--text-primary); display: block; margin-bottom: 4px;">Target Domains</strong>
          <p>${{escapeHtml(domains.join(' \u2022 '))}}</p>
        </div>
      `;
    }}



    function setView(view) {{
      currentView = view;
      document.getElementById('viewBtnTable').classList.toggle('active', view === 'table');
      document.getElementById('viewBtnCards').classList.toggle('active', view === 'cards');
      document.getElementById('tableView').style.display = view === 'table' ? 'block' : 'none';
      document.getElementById('cardsView').classList.toggle('active', view === 'cards');
      render();
    }}

    function setSort(mode) {{
      const sel = document.getElementById('sortSelect');
      if (sel) sel.value = mode;
      render();
    }}

    function toggleMobileFilters() {{
      const drawer = document.getElementById('filtersDrawer');
      if (drawer) drawer.classList.toggle('mobile-open');
    }}

    function toggleDetails(idx) {{
      const row = document.getElementById('details-' + idx);
      if (row) row.classList.toggle('open');
    }}

    function getFilteredOpenings() {{
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const sortMode = (document.getElementById('sortSelect').value || 'fit_recency');
      const fitFilter = document.getElementById('fitFilter').value;
      const categoryFilter = document.getElementById('categoryFilter').value;
      const companyFilter = document.getElementById('companyFilter').value;
      const statusFilter = document.getElementById('statusFilter').value;
      const activeOnly = document.getElementById('activeOnlyToggle').checked;

      return OPENINGS.filter(r => {{
        const score = parseFloat(r.fit_score || 0);
        if (activeOnly && !isRoleActive(r)) return false;
        if (fitFilter === '5' && score < 5) return false;
        if (fitFilter === '4' && (score < 4 || score >= 5)) return false;
        if (fitFilter === '3' && (score < 3 || score >= 4)) return false;
        if (categoryFilter !== 'all' && r.company_category !== categoryFilter) return false;
        if (companyFilter !== 'all' && (r.company || '').trim() !== companyFilter) return false;
        if (statusFilter !== 'all' && (r.status || 'Not Applied') !== statusFilter) return false;
        if (query) {{
          const haystack = [
            r.title, r.company, r.team, r.location, r.req_id, r.fit_rationale,
            r.company_category, r.date_discovered, ...(r.skills_matched || [])
          ].filter(Boolean).join(' ').toLowerCase();
          if (!haystack.includes(query)) return false;
        }}
        return true;
      }}).sort((a, b) => {{
        const scoreA = parseFloat(a.fit_score || 0);
        const scoreB = parseFloat(b.fit_score || 0);
        const dateA = String(a.date_discovered || '');
        const dateB = String(b.date_discovered || '');
        const compA = String(a.company || '').toLowerCase();
        const compB = String(b.company || '').toLowerCase();

        if (sortMode === 'newest') {{
          if (dateB !== dateA) return dateB.localeCompare(dateA);
          return scoreB - scoreA;
        }}
        if (sortMode === 'fit_score') {{
          if (scoreB !== scoreA) return scoreB - scoreA;
          return compA.localeCompare(compB);
        }}
        if (sortMode === 'company') {{
          if (compA !== compB) return compA.localeCompare(compB);
          return scoreB - scoreA;
        }}
        // Default: fit_recency
        if (scoreB !== scoreA) return scoreB - scoreA;
        return dateB.localeCompare(dateA);
      }});
    }}

    function urlTypeBadgeHtml(urlType) {{
      if (urlType === 'board_role_anchor') {{
        return '<span class="url-type-badge url-type-board">Career Board Role</span>';
      }}
      return '<span class="url-type-badge url-type-direct">Direct ATS</span>';
    }}

    function linkPillHtml(r) {{
      if (!isRoleActive(r)) {{
        return '<span class="link-pill link-pill-dead">Closed / Inactive</span>';
      }}
      if (r.link_status === 'restricted' || r.link_status === 'rate_limited') {{
        return '<span class="link-pill link-pill-restricted">Official ATS</span>';
      }}
      return '<span class="link-pill link-pill-active">Active Link</span>';
    }}



    function renderTable(items) {{
      const tbody = document.getElementById('tableBody');
      if (items.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding: 36px; color: var(--text-muted);">No matching openings found. Try adjusting your filters.</td></tr>';
        return;
      }}

      tbody.innerHTML = items.map((r, idx) => {{
        const score = parseFloat(r.fit_score || 0);
        const badgeClass = score >= 5 ? 'badge-5' : (score >= 4 ? 'badge-4' : 'badge-3');
        const badgeText = score >= 5 ? '5★ Direct Fit' : (score >= 4 ? '4★ Strong Fit' : '3★ Match');
        const status = r.status || 'Not Applied';
        const catClass = r.company_category === 'Startup / Emerging' ? 'cat-startup' : 'cat-enterprise';
        const skills = Array.isArray(r.skills_matched) ? r.skills_matched : [];
        const skillsHtml = skills.slice(0, 3).map(s => `<span class="skill-chip">${{escapeHtml(s)}}</span>`).join('') +
          (skills.length > 3 ? `<span style="font-size:11px; color:var(--text-muted);">+${{skills.length - 3}}</span>` : '');

        return `
          <tr class="job-row">
            <td><span class="badge ${{badgeClass}}">${{escapeHtml(badgeText)}}</span></td>
            <td>
              <span class="role-cell">
                <a href="javascript:void(0)" onclick="toggleDetails(${{idx}})" style="color:var(--text-primary); text-decoration:none;">
                  ${{escapeHtml(r.title)}}
                </a>
              </span>
              <div class="company-cell">
                <span>${{escapeHtml(r.company)}}</span>
                <span class="category-chip ${{catClass}}">${{escapeHtml(r.company_category || 'Enterprise / OEM')}}</span>
              </div>
            </td>
            <td>
              <div style="font-weight: 500;">${{escapeHtml(r.location || 'Bangalore')}}</div>
              <div style="font-size: 11px; color: var(--text-muted);">${{escapeHtml(r.team || 'Systems Engineering')}} &bull; Req: ${{escapeHtml(r.req_id || 'N/A')}}</div>
            </td>
            <td class="date-mono">${{escapeHtml(r.date_discovered || '—')}}</td>
            <td>${{skillsHtml || '<span style="color:var(--text-muted);font-size:11px;">None listed</span>'}}</td>
            <td>
              <div style="display:flex; flex-direction:column; gap:4px; align-items:flex-start;">
                ${{linkPillHtml(r)}}
                ${{urlTypeBadgeHtml(r.url_type)}}
              </div>
            </td>
            <td><span class="skill-chip">${{escapeHtml(status)}}</span></td>
            <td style="text-align: right;">
              <a href="${{safeUrl(r.apply_url)}}" target="_blank" rel="noopener noreferrer" class="btn-apply-sm">Apply &rarr;</a>
            </td>
          </tr>
          <tr id="details-${{idx}}" class="details-row">
            <td colspan="8">
              <div class="details-content">
                <strong>AI Match Rationale:</strong> ${{escapeHtml(r.fit_rationale || 'Direct fit based on aerospace systems engineering background.')}}<br/>
                <span style="display:inline-block; margin-top:4px; font-size:12px; color:var(--text-muted);">
                  <strong>Next Action:</strong> ${{escapeHtml(r.next_action || 'Draft tailored resume')}} &bull;
                  <strong>Seniority:</strong> ${{escapeHtml(r.seniority || 'Lead')}} &bull;
                  <strong>Source:</strong> ${{escapeHtml(r.source || 'Official ATS')}}
                </span>
              </div>
            </td>
          </tr>
        `;
      }}).join('');
    }}

    function renderCards(items) {{
      const container = document.getElementById('cardsView');
      if (items.length === 0) {{
        container.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 36px; color: var(--text-muted);">No matching openings found.</div>';
        return;
      }}

      container.innerHTML = items.map(r => {{
        const score = parseFloat(r.fit_score || 0);
        const badgeClass = score >= 5 ? 'badge-5' : (score >= 4 ? 'badge-4' : 'badge-3');
        const badgeText = score >= 5 ? '5★ Direct Fit' : (score >= 4 ? '4★ Strong Fit' : '3★ Match');
        const status = r.status || 'Not Applied';
        const catClass = r.company_category === 'Startup / Emerging' ? 'cat-startup' : 'cat-enterprise';
        const skillsHtml = (r.skills_matched || []).map(s => `<span class="skill-chip">${{escapeHtml(s)}}</span>`).join('');

        return `
          <div class="job-card">
            <div>
              <div class="card-top">
                <span style="font-size:12px; font-weight:700; color:var(--brand-primary); text-transform:uppercase;">${{escapeHtml(r.company)}}</span>
                <span class="badge ${{badgeClass}}">${{escapeHtml(badgeText)}}</span>
              </div>
              <h2 style="font-size:15px; font-weight:700; margin-bottom:4px; color:var(--text-primary); line-height:1.3;">${{escapeHtml(r.title)}}</h2>
              <div style="font-size:12px; color:var(--text-muted); margin-bottom:8px; display:flex; gap:6px; align-items:center; flex-wrap:wrap;">
                <span>${{escapeHtml(r.location || 'Bangalore')}}</span>
                <span>&bull;</span>
                <span class="date-mono">${{escapeHtml(r.date_discovered || '—')}}</span>
                <span class="category-chip ${{catClass}}">${{escapeHtml(r.company_category || 'Enterprise / OEM')}}</span>
              </div>
              <div style="display:flex; gap:6px; margin-bottom:8px; flex-wrap:wrap;">
                ${{linkPillHtml(r)}}
                ${{urlTypeBadgeHtml(r.url_type)}}
              </div>
              <div style="background:#f8fafc; border-left:3px solid var(--brand-primary); padding:6px 10px; font-size:12px; color:var(--text-secondary); margin-bottom:10px;">
                ${{escapeHtml(r.fit_rationale || 'Direct fit based on aerospace systems background.')}}
              </div>
              <div style="margin-bottom:10px;">${{skillsHtml}}</div>
            </div>
            <div class="card-footer">
              <span class="skill-chip">${{escapeHtml(status)}}</span>
              <a href="${{safeUrl(r.apply_url)}}" target="_blank" rel="noopener noreferrer" class="btn-apply-sm">Apply &rarr;</a>
            </div>
          </div>
        `;
      }}).join('');
    }}

    function render() {{
      const items = getFilteredOpenings();
      document.getElementById('matching-count').textContent = items.length;

      const tagContainer = document.getElementById('active-tag-container');
      const activeOnly = document.getElementById('activeOnlyToggle').checked;
      const fitFilter = document.getElementById('fitFilter').value;
      const categoryFilter = document.getElementById('categoryFilter').value;
      const companyFilter = document.getElementById('companyFilter').value;

      const tags = [];
      if (activeOnly) tags.push('<span class="active-tag">Active Jobs Only</span>');
      if (fitFilter !== 'all') tags.push(`<span class="active-tag">${{escapeHtml(fitFilter)}}★ Fits</span>`);
      if (categoryFilter !== 'all') tags.push(`<span class="active-tag">${{escapeHtml(categoryFilter)}}</span>`);
      if (companyFilter !== 'all') tags.push(`<span class="active-tag">${{escapeHtml(companyFilter)}}</span>`);
      tagContainer.innerHTML = tags.join('');

      if (currentView === 'table') {{
        renderTable(items);
      }} else {{
        renderCards(items);
      }}
    }}

    function applyFilters() {{
      render();
    }}

    function toggleDrawer() {{
      const drawer = document.getElementById('candidateDrawer');
      const overlay = document.getElementById('drawerOverlay');
      const isOpen = drawer.classList.contains('open');
      drawer.classList.toggle('open', !isOpen);
      overlay.style.display = isOpen ? 'none' : 'block';
    }}

    document.addEventListener('DOMContentLoaded', () => {{
      populateCompanyFilter();
      renderCandidateDrawer();
      updateKpis();
      render();
    }});
  </script>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")
    logger.info("Successfully generated single-page portal at: %s", output_path)
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate static HTML job hunt portal.")
    parser.add_argument("--openings", type=Path, default=DEFAULT_OPENINGS_PATH, help="Path to openings.json")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE_PATH, help="Path to candidate.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH, help="Output path for HTML")
    args = parser.parse_args()

    build_site(openings_path=args.openings, candidate_path=args.candidate, output_path=args.output)
