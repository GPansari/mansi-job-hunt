#!/usr/bin/env python3
"""Static Site Generator for Mansi Agrawal's Job Hunt Portal.

Generates a modern, clean light-themed single-page application at docs/index.html.
Features:
- Light theme (B2B SaaS / clean enterprise aesthetic)
- Compact, single-row filter bar to minimize vertical space
- Tabular List View (Default) with sortable columns and expandable drawer rows
- Grid Card View (Toggleable)
- Active / Validated jobs filter enabled by default
- Company Category filter (Enterprise / OEM vs Startup / Emerging)
- Application status tracker persisted in localStorage
- Slide-out Candidate Profile Reference Drawer
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

    # Assign company_category if missing
    for r in openings:
        if "company_category" not in r:
            comp = (r.get("company") or "").lower()
            if any(s in comp for s in ["sarla", "ideaforge", "digantara", "galaxeye", "reorbit", "acron", "newspace"]):
                r["company_category"] = "Startup / Emerging"
            else:
                r["company_category"] = "Enterprise / OEM"

    total_count = len(openings)
    fit_5_count = sum(1 for r in openings if float(r.get("fit_score", 0) or 0) >= 5)
    fit_4_count = sum(1 for r in openings if 4 <= float(r.get("fit_score", 0) or 0) < 5)
    active_count = sum(1 for r in openings if r.get("link_status") in ("active", "rate_limited", "restricted", None))

    openings_json_str = json.dumps(openings)
    candidate_json_str = json.dumps(candidate)
    generated_at = datetime.now().strftime("%B %d, %Y")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mansi Agrawal &bull; Aerospace & MBSE Career Portal</title>
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
      --brand-surface: #f0f9ff;
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

    /* Top Navigation Bar */
    header {{
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      padding: 12px 24px;
      position: sticky;
      top: 0;
      z-index: 50;
      box-shadow: var(--shadow-sm);
    }}
    .header-inner {{
      max-width: 1400px;
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
      gap: 10px;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 600;
      padding: 8px 14px;
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
    .btn-primary {{
      background: var(--brand-primary);
      color: #ffffff;
    }}
    .btn-primary:hover {{
      background: var(--brand-hover);
    }}

    /* Main Container */
    main {{
      max-width: 1400px;
      margin: 20px auto 40px auto;
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
      margin-bottom: 16px;
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

    /* Compact Toolbar & Filter Bar - Sticky on Scroll */
    .toolbar-container {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 10px 16px;
      margin-bottom: 16px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      position: sticky;
      top: 69px;
      z-index: 40;
    }}
    .toolbar-left {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      flex: 1;
      min-width: 320px;
    }}
    .search-box {{
      position: relative;
      flex: 1;
      min-width: 240px;
      max-width: 380px;
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
      transition: all 0.15s ease;
    }}
    .search-input:focus {{
      outline: none;
      border-color: var(--border-focus);
      background: #ffffff;
      box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.12);
    }}
    .select-filter {{
      padding: 7px 10px;
      border-radius: 6px;
      border: 1px solid var(--border-medium);
      font-size: 13px;
      font-weight: 500;
      background: #ffffff;
      color: var(--text-primary);
      cursor: pointer;
      outline: none;
    }}
    .select-filter:focus {{
      border-color: var(--border-focus);
    }}

    /* Checkbox Pill for Active Only */
    .active-toggle {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      font-weight: 600;
      padding: 6px 12px;
      background: var(--green-bg);
      border: 1px solid var(--green-border);
      color: var(--green-text);
      border-radius: 6px;
      cursor: pointer;
      user-select: none;
      transition: all 0.15s ease;
    }}
    .active-toggle input {{
      cursor: pointer;
      accent-color: #059669;
    }}

    /* View Switcher */
    .view-switcher {{
      display: inline-flex;
      background: #f1f5f9;
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 2px;
    }}
    .view-btn {{
      padding: 6px 10px;
      border-radius: 4px;
      border: none;
      background: transparent;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      transition: all 0.15s ease;
    }}
    .view-btn.active {{
      background: #ffffff;
      color: var(--brand-primary);
      box-shadow: var(--shadow-sm);
    }}

    /* Filter Tag Pills (Active Filters row) */
    .active-filters-bar {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 14px;
      flex-wrap: wrap;
    }}
    .active-tag {{
      background: #e0f2fe;
      color: #0369a1;
      padding: 2px 8px;
      border-radius: 4px;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .active-tag span {{
      cursor: pointer;
      font-weight: bold;
    }}

    /* Tabular List View (Default) */
    .table-container {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      overflow: hidden;
      box-shadow: var(--shadow-sm);
    }}
    table.jobs-table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }}
    table.jobs-table th {{
      background: #f8fafc;
      color: var(--text-muted);
      font-weight: 600;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      padding: 12px 16px;
      border-bottom: 1px solid var(--border-subtle);
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }}
    table.jobs-table th:hover {{
      color: var(--text-primary);
    }}
    table.jobs-table td {{
      padding: 14px 16px;
      border-bottom: 1px solid var(--border-subtle);
      vertical-align: middle;
    }}
    table.jobs-table tr.job-row {{
      transition: background 0.15s ease;
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
    }}
    .category-chip {{
      font-size: 10px;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }}
    .cat-enterprise {{
      background: #e2e8f0;
      color: #334155;
    }}
    .cat-startup {{
      background: #fef3c7;
      color: #92400e;
    }}

    /* Badges */
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

    .status-select-sm {{
      padding: 5px 8px;
      border-radius: 6px;
      border: 1px solid var(--border-medium);
      font-size: 12px;
      font-weight: 500;
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
      transition: background 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}
    .btn-apply-sm:hover {{
      background: var(--brand-hover);
    }}

    /* Expandable Rationale Details Row */
    .details-row {{
      background: #fafafa;
      display: none;
    }}
    .details-row.open {{
      display: table-row;
    }}
    .details-content {{
      padding: 12px 18px;
      font-size: 13px;
      color: var(--text-secondary);
      border-left: 3px solid var(--brand-primary);
      margin: 8px 16px;
      background: #ffffff;
      border-radius: 0 6px 6px 0;
      box-shadow: var(--shadow-sm);
    }}

    /* Card View (Toggleable) */
    .cards-grid {{
      display: none;
      grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
      gap: 16px;
    }}
    .cards-grid.active {{
      display: grid;
    }}
    .job-card {{
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 18px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-shadow: var(--shadow-sm);
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    }}
    .job-card:hover {{
      transform: translateY(-2px);
      box-shadow: var(--shadow-md);
      border-color: var(--border-medium);
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
      padding-top: 12px;
      margin-top: 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }}

    /* Drawer */
    .drawer-overlay {{
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(15, 23, 42, 0.4);
      backdrop-filter: blur(2px);
      z-index: 99;
    }}
    .drawer {{
      position: fixed;
      top: 0; right: -450px; width: 420px; max-width: 90vw; height: 100vh;
      background: #ffffff;
      box-shadow: -4px 0 24px rgba(0,0,0,0.12);
      z-index: 100;
      transition: right 0.3s cubic-bezier(0.16, 1, 0.3, 1);
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

    /* Responsive adjustments */
    @media (max-width: 900px) {{
      .toolbar-container {{ flex-direction: column; align-items: stretch; }}
      .toolbar-left {{ flex-direction: column; align-items: stretch; }}
      .search-box {{ max-width: 100%; }}
      table.jobs-table th:nth-child(4), table.jobs-table td:nth-child(4) {{ display: none; }}
    }}
  </style>
</head>
<body>

  <!-- Top Navigation Bar -->
  <header>
    <div class="header-inner">
      <div class="brand-title">
        <div class="brand-badge">AEROSPACE</div>
        <div>
          <h1>Mansi Agrawal &bull; Job Hunt Engine</h1>
          <p>10+ Yrs Systems Engineering &bull; MBSE &bull; Lead Engineer @ Boeing India &bull; MS Georgia Tech</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="btn btn-default" onclick="toggleDrawer()">
          <span>👤</span> Candidate Profile
        </button>
      </div>
    </div>
  </header>

  <main>
    <!-- KPI Summary Row -->
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
        <span class="kpi-val" style="color: #6366f1;" id="kpi-actionable">0</span>
        <span class="kpi-label">Actionable (Not Applied)</span>
      </div>
      <div style="margin-left: auto; font-size: 12px; color: var(--text-muted);">
        Synced: <strong>{generated_at}</strong>
      </div>
    </div>

    <!-- Compact Toolbar (Filters + Search + View Switcher) -->
    <div class="toolbar-container">
      <div class="toolbar-left">
        <!-- Instant Search -->
        <div class="search-box">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
          <input type="text" id="searchInput" class="search-input" placeholder="Search title, company, req ID, skill..." oninput="applyFilters()">
        </div>

        <!-- Fit Score Select Filter -->
        <select id="fitFilter" class="select-filter" onchange="applyFilters()">
          <option value="all">Fit: All Scores</option>
          <option value="5">5★ Direct Fits</option>
          <option value="4">4★ Strong Fits</option>
          <option value="3">3★ Moderate Matches</option>
        </select>

        <!-- Company Category Select Filter (Enterprise vs Startup) -->
        <select id="categoryFilter" class="select-filter" onchange="applyFilters()">
          <option value="all">Company Category: All</option>
          <option value="Enterprise / OEM">Enterprise / OEM</option>
          <option value="Startup / Emerging">Startup / Emerging</option>
        </select>

        <!-- Company Name Select Filter -->
        <select id="companyFilter" class="select-filter" onchange="applyFilters()">
          <option value="all">Company: All</option>
          <option value="Airbus">Airbus India</option>
          <option value="Collins">Collins Aerospace</option>
          <option value="Boeing">Boeing India</option>
          <option value="Safran">Safran</option>
          <option value="Thales">Thales</option>
          <option value="Sarla">Sarla Aviation (eVTOL)</option>
          <option value="Digantara">Digantara (Spacetech)</option>
          <option value="ideaForge">ideaForge (UAVs)</option>
          <option value="Quest">Quest Global</option>
          <option value="Tata">Tata Elxsi</option>
        </select>

        <!-- Status Filter -->
        <select id="statusFilter" class="select-filter" onchange="applyFilters()">
          <option value="all">Status: All</option>
          <option value="Not Applied">Not Applied (Pending)</option>
          <option value="Applied">Applied ✅</option>
          <option value="Interviewing">Interviewing 🎯</option>
          <option value="Needs Review">Needs Review ❓</option>
          <option value="Watching">Watching 👁️</option>
        </select>

        <!-- Active Jobs Only Checkbox Toggle (Enabled by default) -->
        <label class="active-toggle" title="Filter out expired or filled job requisitions">
          <input type="checkbox" id="activeOnlyToggle" checked onchange="applyFilters()">
          <span>Active Jobs Only</span>
        </label>
      </div>

      <!-- View Switcher (Table vs Cards) -->
      <div class="view-switcher">
        <button id="viewBtnTable" class="view-btn active" onclick="setView('table')">
          <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M0 2a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V2zm15 2h-4v3h4V4zm0 4h-4v3h4V8zm0 4h-4v3h3a1 1 0 0 0 1-1v-2zm-5 3v-3H6v3h4zm-5 0v-3H1v2a1 1 0 0 0 1 1h3zm-4-4h4V8H1v3zm0-4h4V4H1v3zm5-3v3h4V4H6zm4 4H6v3h4V8z"/></svg>
          Table
        </button>
        <button id="viewBtnCards" class="view-btn" onclick="setView('cards')">
          <svg width="14" height="14" fill="currentColor" viewBox="0 0 16 16"><path d="M1 2.5A1.5 1.5 0 0 1 2.5 1h3A1.5 1.5 0 0 1 7 2.5v3A1.5 1.5 0 0 1 5.5 7h-3A1.5 1.5 0 0 1 1 5.5v-3zm8 0A1.5 1.5 0 0 1 10.5 1h3A1.5 1.5 0 0 1 15 2.5v3A1.5 1.5 0 0 1 13.5 7h-3A1.5 1.5 0 0 1 9 5.5v-3zm-8 8A1.5 1.5 0 0 1 2.5 9h3A1.5 1.5 0 0 1 7 10.5v3A1.5 1.5 0 0 1 5.5 15h-3A1.5 1.5 0 0 1 1 13.5v-3zm8 0A1.5 1.5 0 0 1 10.5 9h3a1.5 1.5 0 0 1 1.5 1.5v3a1.5 1.5 0 0 1-1.5 1.5h-3A1.5 1.5 0 0 1 9 13.5v-3z"/></svg>
          Cards
        </button>
      </div>
    </div>

    <!-- Active Filter Counter Text -->
    <div class="active-filters-bar">
      <span>Showing <strong id="matching-count">0</strong> matching roles</span>
      <span id="active-tag-container" style="display: inline-flex; gap: 6px;"></span>
    </div>

    <!-- 1. Table View (Default) -->
    <div id="tableView" class="table-container">
      <table class="jobs-table">
        <thead>
          <tr>
            <th onclick="sortTable('fit_score')" style="width: 110px;">Fit Score ▾</th>
            <th onclick="sortTable('title')">Role & Company ▾</th>
            <th onclick="sortTable('location')">Location & Team</th>
            <th>Matched Competencies</th>
            <th>Link Status</th>
            <th>Tracker Status</th>
            <th style="text-align: right;">Action</th>
          </tr>
        </thead>
        <tbody id="tableBody">
          <!-- Populated by JS -->
        </tbody>
      </table>
    </div>

    <!-- 2. Cards View (Toggleable) -->
    <div id="cardsView" class="cards-grid">
      <!-- Populated by JS -->
    </div>
  </main>

  <!-- Candidate Profile Reference Drawer -->
  <div id="drawerOverlay" class="drawer-overlay" onclick="toggleDrawer()"></div>
  <aside id="candidateDrawer" class="drawer">
    <div class="drawer-header">
      <h3 class="drawer-title">Mansi Agrawal &bull; Candidate Reference</h3>
      <button class="close-btn" onclick="toggleDrawer()">&times;</button>
    </div>
    <div style="font-size: 13px; color: var(--text-secondary); display: flex; flex-direction: column; gap: 16px;">
      <div>
        <strong style="color: var(--text-primary); display: block; margin-bottom: 4px;">Profile & Experience</strong>
        <p><strong>Current:</strong> Lead Systems Engineer @ Boeing India (Bangalore)</p>
        <p><strong>Experience:</strong> 10+ Years in Aerospace Systems & MBSE</p>
        <p><strong>Education:</strong> MS Aerospace Engineering, Georgia Tech</p>
        <p><strong>Target Location:</strong> Bangalore / Bengaluru (Hybrid / Onsite)</p>
      </div>
      <div>
        <strong style="color: var(--text-primary); display: block; margin-bottom: 6px;">Core Competencies</strong>
        <div style="display: flex; flex-wrap: wrap; gap: 4px;">
          <span class="skill-chip">MBSE</span>
          <span class="skill-chip">Cameo Modeler</span>
          <span class="skill-chip">MagicDraw</span>
          <span class="skill-chip">SysML (v1 & v2)</span>
          <span class="skill-chip">ARP4754A</span>
          <span class="skill-chip">ARP4761</span>
          <span class="skill-chip">DO-178C</span>
          <span class="skill-chip">DO-254</span>
          <span class="skill-chip">IBM DOORS / DNG</span>
          <span class="skill-chip">3DEXPERIENCE</span>
          <span class="skill-chip">ConOps</span>
          <span class="skill-chip">Digital Thread</span>
          <span class="skill-chip">V&V</span>
          <span class="skill-chip">ARINC 429</span>
        </div>
      </div>
      <div>
        <strong style="color: var(--text-primary); display: block; margin-bottom: 4px;">Target Titles</strong>
        <p>Lead Engineer &bull; Staff Systems Engineer &bull; Systems Architecture Manager &bull; MBSE Capability Lead &bull; V&V Lead</p>
      </div>
      <div style="border-top: 1px solid var(--border-subtle); padding-top: 12px;">
        <strong style="color: var(--text-primary); display: block; margin-bottom: 4px;">Autonomous Engine Info</strong>
        <p>Synced with <code>data/openings.json</code> and validated with automated HTTP link auditing.</p>
      </div>
    </div>
  </aside>

  <script>
    const OPENINGS = {openings_json_str};
    let currentView = 'table';
    let sortKey = 'fit_score';
    let sortAsc = false;

    // Local application status persistence
    function getStoredStatus(roleId, defaultStatus) {{
      const saved = localStorage.getItem('status_' + roleId);
      return saved || defaultStatus || 'Not Applied';
    }}

    function setStoredStatus(roleId, newStatus) {{
      localStorage.setItem('status_' + roleId, newStatus);
      updateKpis();
    }}

    function updateKpis() {{
      let actionable = 0;
      OPENINGS.forEach(r => {{
        const s = getStoredStatus(r.id, r.status);
        if (s === 'Not Applied' || s === 'Needs Review') {{
          actionable++;
        }}
      }});
      const el = document.getElementById('kpi-actionable');
      if (el) el.textContent = actionable;
    }}

    function setView(view) {{
      currentView = view;
      document.getElementById('viewBtnTable').classList.toggle('active', view === 'table');
      document.getElementById('viewBtnCards').classList.toggle('active', view === 'cards');
      document.getElementById('tableView').style.display = view === 'table' ? 'block' : 'none';
      document.getElementById('cardsView').classList.toggle('active', view === 'cards');
      render();
    }}

    function sortTable(key) {{
      if (sortKey === key) {{
        sortAsc = !sortAsc;
      }} else {{
        sortKey = key;
        sortAsc = (key === 'title' || key === 'company');
      }}
      render();
    }}

    function toggleDetails(idx) {{
      const row = document.getElementById('details-' + idx);
      if (row) {{
        row.classList.toggle('open');
      }}
    }}

    function getFilteredOpenings() {{
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const fitFilter = document.getElementById('fitFilter').value;
      const categoryFilter = document.getElementById('categoryFilter').value;
      const companyFilter = document.getElementById('companyFilter').value;
      const statusFilter = document.getElementById('statusFilter').value;
      const activeOnly = document.getElementById('activeOnlyToggle').checked;

      return OPENINGS.filter(r => {{
        const score = parseFloat(r.fit_score || 0);

        // Active only filter
        if (activeOnly) {{
          if (r.link_status === 'dead' || r.link_status === 'expired') return false;
        }}

        // Fit filter
        if (fitFilter === '5' && score < 5) return false;
        if (fitFilter === '4' && (score < 4 || score >= 5)) return false;
        if (fitFilter === '3' && (score < 3 || score >= 4)) return false;

        // Category filter
        if (categoryFilter !== 'all') {{
          if (r.company_category !== categoryFilter) return false;
        }}

        // Company filter
        if (companyFilter !== 'all') {{
          const comp = (r.company || '').toLowerCase();
          if (!comp.includes(companyFilter.toLowerCase())) return false;
        }}

        // Status filter
        if (statusFilter !== 'all') {{
          const currentStatus = getStoredStatus(r.id, r.status);
          if (currentStatus !== statusFilter) return false;
        }}

        // Search text
        if (query) {{
          const haystack = [
            r.title, r.company, r.team, r.location, r.req_id, r.fit_rationale,
            r.company_category, ...(r.skills_matched || [])
          ].filter(Boolean).join(' ').toLowerCase();
          if (!haystack.includes(query)) return false;
        }}

        return true;
      }}).sort((a, b) => {{
        let valA = a[sortKey];
        let valB = b[sortKey];
        if (sortKey === 'fit_score') {{
          valA = parseFloat(valA || 0);
          valB = parseFloat(valB || 0);
        }} else {{
          valA = (valA || '').toString().toLowerCase();
          valB = (valB || '').toString().toLowerCase();
        }}
        if (valA < valB) return sortAsc ? -1 : 1;
        if (valA > valB) return sortAsc ? 1 : -1;
        return 0;
      }});
    }}

    function renderTable(items) {{
      const tbody = document.getElementById('tableBody');
      if (items.length === 0) {{
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 40px; color: var(--text-muted);">No matching openings found. Try adjusting your filters.</td></tr>`;
        return;
      }}

      tbody.innerHTML = items.map((r, idx) => {{
        const score = parseFloat(r.fit_score || 0);
        let badgeClass = 'badge-3';
        let badgeText = '3★ Match';
        if (score >= 5) {{ badgeClass = 'badge-5'; badgeText = '5★ Direct Fit'; }}
        else if (score >= 4) {{ badgeClass = 'badge-4'; badgeText = '4★ Strong Fit'; }}

        const status = getStoredStatus(r.id, r.status);
        const isDead = (r.link_status === 'dead' || r.link_status === 'expired');

        let linkPill = '';
        if (isDead) {{
          linkPill = '<span class="link-pill link-pill-dead">⚠️ Closed</span>';
        }} else if (r.link_status === 'restricted' || r.link_status === 'rate_limited') {{
          linkPill = '<span class="link-pill link-pill-restricted">⚡ Official ATS</span>';
        }} else {{
          linkPill = '<span class="link-pill link-pill-active">✓ Active Link</span>';
        }}

        const catClass = (r.company_category === 'Startup / Emerging') ? 'cat-startup' : 'cat-enterprise';
        const skillsHtml = (r.skills_matched || []).slice(0, 3).map(s => `<span class="skill-chip">${{s}}</span>`).join('') +
          ((r.skills_matched || []).length > 3 ? `<span style="font-size:11px; color:var(--text-muted);">+${{r.skills_matched.length - 3}}</span>` : '');

        return `
          <tr class="job-row">
            <td>
              <span class="badge ${{badgeClass}}">${{badgeText}}</span>
            </td>
            <td>
              <span class="role-cell">
                <a href="javascript:void(0)" onclick="toggleDetails(${{idx}})" style="color:var(--text-primary); text-decoration:none;" title="Click for AI rationale and details">
                  ${{r.title}} <span style="font-size:11px; color:var(--brand-primary); font-weight:normal;">ℹ️</span>
                </a>
              </span>
              <div class="company-cell">
                <span>${{r.company}}</span>
                <span class="category-chip ${{catClass}}">${{r.company_category || 'Enterprise'}}</span>
              </div>
            </td>
            <td>
              <div style="font-weight: 500;">${{r.location || 'Bangalore'}}</div>
              <div style="font-size: 11px; color: var(--text-muted);">${{r.team || 'Systems Engineering'}} &bull; Req: ${{r.req_id || 'N/A'}}</div>
            </td>
            <td>
              <div>${{skillsHtml || '<span style="color:var(--text-muted);font-size:11px;">None listed</span>'}}</div>
            </td>
            <td>
              ${{linkPill}}
            </td>
            <td>
              <select class="status-select-sm" onchange="setStoredStatus('${{r.id}}', this.value)">
                <option value="Not Applied" ${{status === 'Not Applied' ? 'selected' : ''}}>Not Applied</option>
                <option value="Applied" ${{status === 'Applied' ? 'selected' : ''}}>Applied ✅</option>
                <option value="Interviewing" ${{status === 'Interviewing' ? 'selected' : ''}}>Interviewing 🎯</option>
                <option value="Needs Review" ${{status === 'Needs Review' ? 'selected' : ''}}>Needs Review ❓</option>
                <option value="Watching" ${{status === 'Watching' ? 'selected' : ''}}>Watching 👁️</option>
              </select>
            </td>
            <td style="text-align: right;">
              <a href="${{r.apply_url || '#'}}" target="_blank" rel="noopener noreferrer" class="btn-apply-sm">
                Apply &rarr;
              </a>
            </td>
          </tr>
          <tr id="details-${{idx}}" class="details-row">
            <td colspan="7">
              <div class="details-content">
                <strong>AI Match Rationale:</strong> "${{r.fit_rationale || 'Direct fit based on aerospace systems engineering background.'}}"<br/>
                <span style="display:inline-block; margin-top:4px; font-size:12px; color:var(--text-muted);">
                  <strong>Next Action:</strong> ${{r.next_action || 'Draft tailored resume'}} &bull; <strong>Seniority:</strong> ${{r.seniority || 'Lead'}}
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
        container.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-muted);">No matching openings found.</div>`;
        return;
      }}

      container.innerHTML = items.map(r => {{
        const score = parseFloat(r.fit_score || 0);
        let badgeClass = 'badge-3';
        let badgeText = '3★ Match';
        if (score >= 5) {{ badgeClass = 'badge-5'; badgeText = '5★ Direct Fit'; }}
        else if (score >= 4) {{ badgeClass = 'badge-4'; badgeText = '4★ Strong Fit'; }}

        const status = getStoredStatus(r.id, r.status);
        const isDead = (r.link_status === 'dead' || r.link_status === 'expired');

        let linkPill = isDead
          ? '<span class="link-pill link-pill-dead">⚠️ Closed</span>'
          : '<span class="link-pill link-pill-active">✓ Active Link</span>';

        const catClass = (r.company_category === 'Startup / Emerging') ? 'cat-startup' : 'cat-enterprise';
        const skillsHtml = (r.skills_matched || []).map(s => `<span class="skill-chip">${{s}}</span>`).join('');

        return `
          <div class="job-card">
            <div>
              <div class="card-top">
                <span style="font-size:12px; font-weight:700; color:var(--brand-primary); text-transform:uppercase;">${{r.company}}</span>
                <span class="badge ${{badgeClass}}">${{badgeText}}</span>
              </div>
              <h2 style="font-size:15px; font-weight:700; margin-bottom:4px; color:var(--text-primary); line-height:1.3;">${{r.title}}</h2>
              <div style="font-size:12px; color:var(--text-muted); margin-bottom:8px; display:flex; gap:6px; align-items:center;">
                <span>📍 ${{r.location || 'Bangalore'}}</span>
                <span>&bull;</span>
                <span class="category-chip ${{catClass}}">${{r.company_category || 'Enterprise'}}</span>
              </div>
              <div style="margin-bottom:8px;">${{linkPill}}</div>
              <div style="background:#f8fafc; border-left:3px solid var(--brand-primary); padding:6px 10px; font-size:12px; color:var(--text-secondary); margin-bottom:10px; border-radius:0 4px 4px 0;">
                "${{r.fit_rationale || 'Direct fit based on aerospace systems background.'}}"
              </div>
              <div style="margin-bottom:10px;">${{skillsHtml}}</div>
            </div>
            <div class="card-footer">
              <select class="status-select-sm" onchange="setStoredStatus('${{r.id}}', this.value)">
                <option value="Not Applied" ${{status === 'Not Applied' ? 'selected' : ''}}>Not Applied</option>
                <option value="Applied" ${{status === 'Applied' ? 'selected' : ''}}>Applied ✅</option>
                <option value="Interviewing" ${{status === 'Interviewing' ? 'selected' : ''}}>Interviewing 🎯</option>
                <option value="Needs Review" ${{status === 'Needs Review' ? 'selected' : ''}}>Needs Review ❓</option>
                <option value="Watching" ${{status === 'Watching' ? 'selected' : ''}}>Watching 👁️</option>
              </select>
              <a href="${{r.apply_url || '#'}}" target="_blank" rel="noopener noreferrer" class="btn-apply-sm">
                Apply &rarr;
              </a>
            </div>
          </div>
        `;
      }}).join('');
    }}

    function render() {{
      const items = getFilteredOpenings();
      document.getElementById('matching-count').textContent = items.length;

      // Update active tag indicators
      const tagContainer = document.getElementById('active-tag-container');
      const activeOnly = document.getElementById('activeOnlyToggle').checked;
      const fitFilter = document.getElementById('fitFilter').value;
      const categoryFilter = document.getElementById('categoryFilter').value;

      let tags = [];
      if (activeOnly) tags.push('<span class="active-tag">Active Jobs Only</span>');
      if (fitFilter !== 'all') tags.push(`<span class="active-tag">${{fitFilter}}★ Fits</span>`);
      if (categoryFilter !== 'all') tags.push(`<span class="active-tag">${{categoryFilter}}</span>`);
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
      if (isOpen) {{
        drawer.classList.remove('open');
        overlay.style.display = 'none';
      }} else {{
        drawer.classList.add('open');
        overlay.style.display = 'block';
      }}
    }}

    document.addEventListener('DOMContentLoaded', () => {{
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
