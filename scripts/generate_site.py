#!/usr/bin/env python3
"""Static Site Generator for Mansi Agrawal's Job Hunt Portal.

Compiles data/openings.json and profile/candidate.json into a modern,
responsive single-page dashboard at docs/index.html for GitHub Pages / Cloudflare Pages.
Includes interactive search, multi-axis filtering, link verification badges,
application tracking (localStorage), and candidate profile drawer.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import logging
from pathlib import Path
import sys
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

    # Metrics
    total_count = len(openings)
    fit_5_count = sum(1 for r in openings if float(r.get("fit_score", 0) or 0) >= 5)
    fit_4_count = sum(1 for r in openings if 4 <= float(r.get("fit_score", 0) or 0) < 5)
    fit_3_count = sum(1 for r in openings if 3 <= float(r.get("fit_score", 0) or 0) < 4)
    active_links_count = sum(1 for r in openings if r.get("link_status") in ("active", "rate_limited", "restricted", None))

    openings_json_str = json.dumps(openings)
    candidate_json_str = json.dumps(candidate)
    generated_at = datetime.now().strftime("%B %d, %Y")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mansi Agrawal | Aerospace Systems Engineering & MBSE Portal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --card-border: #1f2937;
      --card-hover: #1e293b;
      --text-main: #f9fafb;
      --text-muted: #9ca3af;
      --accent-blue: #38bdf8;
      --accent-cyan: #06b6d4;
      --accent-green: #10b981;
      --accent-amber: #f59e0b;
      --accent-red: #ef4444;
      --pill-bg: #1f2937;
      --pill-text: #e5e7eb;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg);
      color: var(--text-main);
      min-height: 100vh;
      line-height: 1.5;
      padding-bottom: 60px;
    }}
    header {{
      background: linear-gradient(180deg, #131b2e 0%, #0b0f19 100%);
      border-bottom: 1px solid var(--card-border);
      padding: 32px 24px;
      position: sticky;
      top: 0;
      z-index: 40;
      backdrop-filter: blur(8px);
    }}
    .header-container {{
      max-width: 1300px;
      margin: 0 auto;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
    }}
    .candidate-info h1 {{
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(90deg, #ffffff 0%, #38bdf8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .candidate-info p {{
      color: var(--text-muted);
      font-size: 14px;
      margin-top: 4px;
    }}
    .header-actions {{
      display: flex;
      gap: 12px;
      align-items: center;
    }}
    .btn {{
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s ease;
      border: 1px solid transparent;
    }}
    .btn-primary {{
      background-color: #0284c7;
      color: #ffffff;
    }}
    .btn-primary:hover {{
      background-color: #0369a1;
    }}
    .btn-outline {{
      background: #1f2937;
      color: #e5e7eb;
      border-color: #374151;
    }}
    .btn-outline:hover {{
      background: #374151;
    }}
    .main-container {{
      max-width: 1300px;
      margin: 24px auto 0 auto;
      padding: 0 24px;
    }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 14px;
      margin-bottom: 24px;
    }}
    .metric-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
    }}
    .metric-val {{
      font-size: 28px;
      font-weight: 800;
      color: #ffffff;
      font-family: 'JetBrains Mono', monospace;
    }}
    .metric-label {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.8px;
      margin-top: 2px;
    }}
    .controls-panel {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 18px 20px;
      margin-bottom: 24px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }}
    .search-row {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .search-input {{
      flex: 1;
      min-width: 260px;
      padding: 10px 14px;
      border-radius: 8px;
      background: #0b0f19;
      border: 1px solid #374151;
      color: #ffffff;
      font-size: 14px;
    }}
    .search-input:focus {{
      outline: none;
      border-color: var(--accent-blue);
    }}
    .filter-pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .filter-btn {{
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 500;
      background: #1e293b;
      color: #cbd5e1;
      border: 1px solid #334155;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .filter-btn:hover, .filter-btn.active {{
      background: #0284c7;
      color: #ffffff;
      border-color: #38bdf8;
    }}
    .cards-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
      gap: 20px;
    }}
    .job-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: transform 0.15s ease, border-color 0.15s ease;
      position: relative;
    }}
    .job-card:hover {{
      transform: translateY(-2px);
      border-color: #38bdf8;
    }}
    .card-top {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 12px;
      gap: 8px;
    }}
    .company-title {{
      font-size: 13px;
      font-weight: 700;
      color: var(--accent-blue);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .fit-badge {{
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.5px;
      white-space: nowrap;
    }}
    .fit-5 {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid #059669; }}
    .fit-4 {{ background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid #0284c7; }}
    .fit-3 {{ background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid #d97706; }}
    .job-title {{
      font-size: 17px;
      font-weight: 700;
      color: #ffffff;
      line-height: 1.35;
      margin-bottom: 6px;
    }}
    .meta-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 14px;
    }}
    .meta-item {{
      display: flex;
      align-items: center;
      gap: 4px;
    }}
    .rationale-box {{
      background: rgba(15, 23, 42, 0.6);
      border-left: 3px solid #38bdf8;
      padding: 8px 12px;
      border-radius: 0 6px 6px 0;
      font-size: 13px;
      color: #cbd5e1;
      margin-bottom: 14px;
      font-style: italic;
    }}
    .skills-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 16px;
    }}
    .skill-chip {{
      background: var(--pill-bg);
      color: var(--pill-text);
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 6px;
      border: 1px solid #374151;
      font-family: 'JetBrains Mono', monospace;
    }}
    .link-badge {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 6px;
      margin-bottom: 12px;
    }}
    .link-active {{ background: rgba(16, 185, 129, 0.1); color: #10b981; border: 1px solid #047857; }}
    .link-restricted {{ background: rgba(56, 189, 248, 0.1); color: #38bdf8; border: 1px solid #0284c7; }}
    .link-expired {{ background: rgba(239, 68, 68, 0.1); color: #f87171; border: 1px solid #b91c1c; }}
    .card-footer {{
      border-top: 1px solid var(--card-border);
      padding-top: 14px;
      margin-top: 8px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }}
    .status-select {{
      background: #1e293b;
      color: #cbd5e1;
      border: 1px solid #334155;
      font-size: 12px;
      padding: 6px 10px;
      border-radius: 6px;
      cursor: pointer;
    }}
    .apply-btn {{
      background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%);
      color: #ffffff;
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease;
      box-shadow: 0 2px 4px rgba(2, 132, 199, 0.2);
    }}
    .apply-btn:hover {{
      box-shadow: 0 4px 10px rgba(2, 132, 199, 0.4);
      transform: translateY(-1px);
    }}
    /* Drawer */
    .drawer-overlay {{
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0,0,0,0.7);
      backdrop-filter: blur(4px);
      z-index: 99;
    }}
    .drawer {{
      position: fixed;
      top: 0; right: -420px; width: 400px; max-width: 90vw; height: 100vh;
      background: #111827;
      border-left: 1px solid var(--card-border);
      box-shadow: -4px 0 20px rgba(0,0,0,0.5);
      z-index: 100;
      transition: right 0.3s ease;
      padding: 28px 24px;
      overflow-y: auto;
    }}
    .drawer.open {{ right: 0; }}
    .drawer-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 12px;
    }}
    .drawer-title {{ font-size: 18px; font-weight: 700; color: #ffffff; }}
    .close-btn {{ background: none; border: none; color: var(--text-muted); font-size: 22px; cursor: pointer; }}
  </style>
</head>
<body>

  <header>
    <div class="header-container">
      <div class="candidate-info">
        <h1>Mansi Agrawal &bull; Opportunities Review Portal</h1>
        <p>10+ Yrs Aerospace Systems Engineering &bull; MBSE &bull; Lead Systems Engineer @ Boeing India &bull; MS Georgia Tech</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-outline" onclick="toggleDrawer()">
          <span>👤</span> Candidate Profile
        </button>
        <a href="https://mail.google.com" target="_blank" class="btn btn-primary">
          <span>✉️</span> Gmail Digest
        </a>
      </div>
    </div>
  </header>

  <main class="main-container">
    <!-- Top KPI Metrics -->
    <div class="metrics-grid">
      <div class="metric-card">
        <span class="metric-val">{total_count}</span>
        <span class="metric-label">Total Tracked Roles</span>
      </div>
      <div class="metric-card">
        <span class="metric-val" style="color: #34d399;">{fit_5_count}</span>
        <span class="metric-label">Direct Matches (5★)</span>
      </div>
      <div class="metric-card">
        <span class="metric-val" style="color: #38bdf8;">{fit_4_count}</span>
        <span class="metric-label">Strong Fits (4★)</span>
      </div>
      <div class="metric-card">
        <span class="metric-val" style="color: #60a5fa;" id="actionable-count">0</span>
        <span class="metric-label">Actionable (Not Applied)</span>
      </div>
      <div class="metric-card">
        <span class="metric-val" style="color: #a78bfa;">{generated_at}</span>
        <span class="metric-label">Sync Cycle</span>
      </div>
    </div>

    <!-- Controls Panel -->
    <div class="controls-panel">
      <div class="search-row">
        <input type="text" id="searchInput" class="search-input" placeholder="Search by job title, company, req ID, or skill (e.g. MBSE, Cameo, Airbus)..." oninput="applyFilters()">
      </div>
      <div class="filter-pills">
        <span style="font-size: 12px; font-weight: 600; color: var(--text-muted); margin-right: 4px;">FIT SCORE:</span>
        <button class="filter-btn active" data-filter="all" onclick="setFitFilter('all', this)">All</button>
        <button class="filter-btn" data-filter="5" onclick="setFitFilter('5', this)">5★ Direct Fits</button>
        <button class="filter-btn" data-filter="4" onclick="setFitFilter('4', this)">4★ Strong Fits</button>
        <button class="filter-btn" data-filter="3" onclick="setFitFilter('3', this)">3★ Matches</button>
      </div>
      <div class="filter-pills">
        <span style="font-size: 12px; font-weight: 600; color: var(--text-muted); margin-right: 4px;">TARGET COMPANY:</span>
        <button class="filter-btn active" onclick="setCompanyFilter('all', this)">All Companies</button>
        <button class="filter-btn" onclick="setCompanyFilter('Airbus', this)">Airbus</button>
        <button class="filter-btn" onclick="setCompanyFilter('Collins', this)">Collins Aerospace</button>
        <button class="filter-btn" onclick="setCompanyFilter('Boeing', this)">Boeing India</button>
        <button class="filter-btn" onclick="setCompanyFilter('Safran', this)">Safran</button>
        <button class="filter-btn" onclick="setCompanyFilter('Thales', this)">Thales</button>
        <button class="filter-btn" onclick="setCompanyFilter('Startups', this)">eVTOL / Space Startups</button>
      </div>
      <div class="filter-pills">
        <span style="font-size: 12px; font-weight: 600; color: var(--text-muted); margin-right: 4px;">LINK STATUS:</span>
        <button class="filter-btn active" onclick="setLinkFilter('all', this)">All Links</button>
        <button class="filter-btn" onclick="setLinkFilter('active_only', this)">Active / Verified Only</button>
      </div>
    </div>

    <!-- Cards Grid -->
    <div id="cardsGrid" class="cards-grid">
      <!-- Generated via JavaScript -->
    </div>
  </main>

  <!-- Candidate Profile Drawer -->
  <div id="drawerOverlay" class="drawer-overlay" onclick="toggleDrawer()"></div>
  <aside id="candidateDrawer" class="drawer">
    <div class="drawer-header">
      <h3 class="drawer-title">Candidate Profile</h3>
      <button class="close-btn" onclick="toggleDrawer()">&times;</button>
    </div>
    <div style="font-size: 13px; color: #cbd5e1; display: flex; flex-direction: column; gap: 16px;">
      <div>
        <strong style="color: #ffffff; display: block; margin-bottom: 4px;">Education & Target</strong>
        <p>MS Aerospace Engineering, Georgia Tech</p>
        <p>10+ Years Experience in Avionics, MBSE, and Systems Engineering</p>
        <p>Current: Lead Systems Engineer @ Boeing India</p>
      </div>
      <div>
        <strong style="color: #ffffff; display: block; margin-bottom: 6px;">Core Competencies</strong>
        <div style="display: flex; flex-wrap: wrap; gap: 6px;">
          <span class="skill-chip">MBSE</span>
          <span class="skill-chip">Cameo Systems Modeler</span>
          <span class="skill-chip">MagicDraw</span>
          <span class="skill-chip">SysML (v1 & v2)</span>
          <span class="skill-chip">ARP4754A</span>
          <span class="skill-chip">ARP4761</span>
          <span class="skill-chip">DO-178C</span>
          <span class="skill-chip">DO-254</span>
          <span class="skill-chip">IBM DOORS</span>
          <span class="skill-chip">3DEXPERIENCE</span>
          <span class="skill-chip">ConOps</span>
          <span class="skill-chip">Digital Thread</span>
          <span class="skill-chip">V&V</span>
          <span class="skill-chip">ARINC 429</span>
        </div>
      </div>
      <div>
        <strong style="color: #ffffff; display: block; margin-bottom: 4px;">Target Titles</strong>
        <p>Lead Engineer &bull; Staff Systems Engineer &bull; Systems Architecture Manager &bull; MBSE Capability Lead &bull; V&V Lead</p>
      </div>
      <div>
        <strong style="color: #ffffff; display: block; margin-bottom: 4px;">Location Preference</strong>
        <p>Bangalore / Bengaluru (Hybrid / Onsite)</p>
      </div>
    </div>
  </aside>

  <script>
    const OPENINGS = {openings_json_str};
    let currentFitFilter = 'all';
    let currentCompanyFilter = 'all';
    let currentLinkFilter = 'all';

    // Local application status persistence
    function getStoredStatus(roleId, defaultStatus) {{
      const saved = localStorage.getItem('status_' + roleId);
      return saved || defaultStatus || 'Not Applied';
    }}

    function setStoredStatus(roleId, newStatus) {{
      localStorage.setItem('status_' + roleId, newStatus);
      updateActionableCount();
    }}

    function updateActionableCount() {{
      let count = 0;
      OPENINGS.forEach(r => {{
        const status = getStoredStatus(r.id, r.status);
        if (status === 'Not Applied' || status === 'Needs Review') {{
          count++;
        }}
      }});
      const el = document.getElementById('actionable-count');
      if (el) el.textContent = count;
    }}

    function renderCards() {{
      const container = document.getElementById('cardsGrid');
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();

      const filtered = OPENINGS.filter(r => {{
        const score = parseFloat(r.fit_score || 0);

        // Fit filter
        if (currentFitFilter === '5' && score < 5) return false;
        if (currentFitFilter === '4' && (score < 4 || score >= 5)) return false;
        if (currentFitFilter === '3' && (score < 3 || score >= 4)) return false;

        // Company filter
        const comp = (r.company || '').toLowerCase();
        if (currentCompanyFilter === 'Airbus' && !comp.includes('airbus')) return false;
        if (currentCompanyFilter === 'Collins' && !comp.includes('collins') && !comp.includes('rtx')) return false;
        if (currentCompanyFilter === 'Boeing' && !comp.includes('boeing')) return false;
        if (currentCompanyFilter === 'Safran' && !comp.includes('safran')) return false;
        if (currentCompanyFilter === 'Thales' && !comp.includes('thales')) return false;
        if (currentCompanyFilter === 'Startups') {{
          const isStartup = ['sarla', 'ideaforge', 'digantara', 'galaxeye', 'reorbit', 'acron', 'newspace'].some(s => comp.includes(s));
          if (!isStartup) return false;
        }}

        // Link filter
        if (currentLinkFilter === 'active_only') {{
          if (r.link_status === 'dead' || r.link_status === 'expired') return false;
        }}

        // Text search
        if (query) {{
          const haystack = [
            r.title, r.company, r.team, r.location, r.req_id, r.fit_rationale,
            ...(r.skills_matched || [])
          ].filter(Boolean).join(' ').toLowerCase();
          if (!haystack.includes(query)) return false;
        }}

        return true;
      }});

      if (filtered.length === 0) {{
        container.innerHTML = `
          <div style="grid-column: 1 / -1; text-align: center; padding: 60px 20px; color: var(--text-muted); background: var(--card-bg); border-radius: 12px; border: 1px dashed var(--card-border);">
            <div style="font-size: 32px; margin-bottom: 12px;">🔍</div>
            <h3 style="color: #ffffff; margin-bottom: 6px;">No matching openings found</h3>
            <p style="font-size: 14px;">Try loosening your search keywords or switching filters back to "All".</p>
          </div>
        `;
        return;
      }}

      container.innerHTML = filtered.map(r => {{
        const score = parseFloat(r.fit_score || 0);
        let fitClass = 'fit-3';
        let fitText = 'Fit 3/5 ★ Moderate';
        if (score >= 5) {{ fitClass = 'fit-5'; fitText = 'Fit 5/5 ★ Direct Match'; }}
        else if (score >= 4) {{ fitClass = 'fit-4'; fitText = 'Fit 4/5 ★ Strong Fit'; }}

        const status = getStoredStatus(r.id, r.status);

        // Link status badge
        let linkBadgeHtml = '';
        if (r.link_status === 'dead' || r.link_status === 'expired') {{
          linkBadgeHtml = '<span class="link-badge link-expired">⚠️ Posting Closed / Expired</span>';
        }} else if (r.link_status === 'restricted' || r.link_status === 'rate_limited') {{
          linkBadgeHtml = '<span class="link-badge link-restricted">⚡ Official Portal (Verified)</span>';
        }} else {{
          linkBadgeHtml = '<span class="link-badge link-active">✓ Verified Active Link</span>';
        }}

        const skillsHtml = (r.skills_matched || []).map(s => `<span class="skill-chip">${{s}}</span>`).join('');

        return `
          <div class="job-card">
            <div>
              <div class="card-top">
                <span class="company-title">${{r.company || 'Aerospace Company'}}</span>
                <span class="fit-badge ${{fitClass}}">${{fitText}}</span>
              </div>
              <h2 class="job-title">${{r.title}}</h2>
              <div class="meta-row">
                <span class="meta-item">📍 ${{r.location || 'Bangalore'}}</span>
                <span class="meta-item">🏢 ${{r.team || 'Systems Engineering'}}</span>
                <span class="meta-item">🔖 Req: ${{r.req_id || 'N/A'}}</span>
                <span class="meta-item">💼 ${{r.seniority || 'Lead'}}</span>
              </div>
              ${{linkBadgeHtml}}
              <div class="rationale-box">
                "${{r.fit_rationale || 'Aligned with aerospace systems background.'}}"
              </div>
              <div class="skills-row">
                ${{skillsHtml}}
              </div>
              <div style="font-size: 12px; color: #94a3b8; margin-bottom: 8px;">
                <strong>Next Step:</strong> ${{r.next_action || 'Draft tailored resume'}}
              </div>
            </div>
            <div class="card-footer">
              <select class="status-select" onchange="setStoredStatus('${{r.id}}', this.value)">
                <option value="Not Applied" ${{status === 'Not Applied' ? 'selected' : ''}}>Not Applied</option>
                <option value="Applied" ${{status === 'Applied' ? 'selected' : ''}}>Applied ✅</option>
                <option value="Interviewing" ${{status === 'Interviewing' ? 'selected' : ''}}>Interviewing 🎯</option>
                <option value="Needs Review" ${{status === 'Needs Review' ? 'selected' : ''}}>Needs Review ❓</option>
                <option value="Watching" ${{status === 'Watching' ? 'selected' : ''}}>Watching 👁️</option>
              </select>
              <a href="${{r.apply_url || '#'}}" target="_blank" rel="noopener noreferrer" class="apply-btn">
                Apply Online &rarr;
              </a>
            </div>
          </div>
        `;
      }}).join('');
    }}

    function applyFilters() {{
      renderCards();
    }}

    function setFitFilter(fit, btn) {{
      currentFitFilter = fit;
      btn.parentElement.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderCards();
    }}

    function setCompanyFilter(company, btn) {{
      currentCompanyFilter = company;
      btn.parentElement.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderCards();
    }}

    function setLinkFilter(filterType, btn) {{
      currentLinkFilter = filterType;
      btn.parentElement.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderCards();
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

    // Initial render
    document.addEventListener('DOMContentLoaded', () => {{
      updateActionableCount();
      renderCards();
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
