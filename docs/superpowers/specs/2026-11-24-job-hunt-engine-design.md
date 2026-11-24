# Design Spec: Autonomous Job Hunt Engine for Mansi Agrawal

**Date:** 2026-11-24  
**Status:** In Review  
**Target Candidate:** Mansi Agrawal (Lead Systems Engineer, Boeing India, MS Georgia Tech, 10 yrs exp, MBSE / SysML / Cameo / DOORS / ARP4754A)  
**Target Market:** Bangalore, India — Aerospace & Defense (Commercial Aircraft, UAVs, eVTOL, Spacetech)  

---

## 1. Intent and The Why

Mansi is an accomplished Lead Systems Engineer leading digital transformation and MBSE adoption for commercial aircraft (777-8F) and UAV programs. This repository is intended to be an autonomous, best-in-class job hunting command center. 

The primary goal is to relieve Mansi from tedious manual job board browsing by:
1. Maintaining a clean, machine-actionable single source of truth for target companies and active job opportunities.
2. Continuously discovering relevant high-fit openings across multiple channels (public web/Google dorking, direct ATS endpoints, safe LinkedIn searches).
3. Automatically scoring and filtering roles against Mansi's specific technical skills and seniority criteria.
4. Sending curated weekly email digests to Mansi (`agrawal.mansi20@gmail.com`) via the connected Gmail account.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Clean Repo Architecture:** Reorganize the workspace into a modular hierarchy (`profile/`, `data/`, `scripts/`, `reports/`, `archive/`).
- **Structured Data:** Single source of truth in JSON (`target_companies.json`, `openings.json`, `candidate.json`) with automated synchronization to human-readable Markdown (`data/Openings_Tracker.md`).
- **Multi-Channel Discovery:**
  - *Tier 1:* Google search dorking targeting public LinkedIn job postings (`site:linkedin.com/jobs ("MBSE" OR "SysML") ("Bangalore" OR "Bengaluru")`) and aggregator feeds with zero account risk.
  - *Tier 2:* Direct public ATS monitors (Workday for Airbus/Collins/GE; Greenhouse/Lever/Ashby for startups like Sarla Aviation, Pixxel, Bellatrix, NewSpace).
  - *Tier 3:* Safe LinkedIn inspection with strict human-mimicking safety guardrails.
- **Automated Fit Scoring (1–5):** Rule-based matcher comparing role descriptions with Mansi's core proficiencies (SysML, Cameo, DOORS, 3DEXPERIENCE, ARP4754A, Systems Architecture, V&V).
- **Weekly Email Digest:** Direct delivery via the native Gmail integration (`imgauravpansari@gmail.com`) with executive summaries, direct application links, and actionable next steps.
- **Agent Operating Manual (`GEMINI.md`):** Complete repo instructions for AI agents operating this workspace.

### Non-Goals
- Automated direct applications (auto-filling forms or submitting resumes automatically without human oversight). All applications must remain human-verified.
- Cold mass-messaging or automated LinkedIn connection requests (violates LinkedIn safety rules).

### Anti-Goals
- Scrapes that trigger LinkedIn anti-bot detection or risk account safety.
- Cluttering the tracker with junior/fresher roles or non-aerospace pure web/software engineering titles.
- Corrupting or losing historical data currently stored across Excel and Word files.

---

## 3. Constraints & Operational Decisions

### Email Delivery Policy (User Confirmed)
- **Mode:** Direct Send via `gmail mutate send`.
- **Recipient:** `agrawal.mansi20@gmail.com`.
- **Sender/Operator:** Connected account `imgauravpansari@gmail.com`.
- **Failsafe Delivery Gates:**
  1. *De-duplication:* Never email a role that has already been dispatched in a previous digest.
  2. *Relevance Threshold:* Only roles with a calculated `fit_score >= 3` are included in the digest.
  3. *Validation:* URLs and Requisition IDs are validated before inclusion.

### Orchestration & Search Architecture (User Confirmed)
- **Model:** **Agent-Orchestrated Workflow**.
- **Execution:** Triggered via scheduled Antigravity background automation or on-demand via the agent commands defined in `GEMINI.md`.
- **Discovery Strategy:**
  - The AI Agent conducts intelligent multi-channel web searches (Tier 1 Google Dorking for public LinkedIn job listings, Google Jobs, etc.) eliminating the risk of headless scraper blocks and 999 IP rate limits.
  - Python scripts (`scripts/search_engine.py`, `scripts/scorer.py`, `scripts/notifier.py`, `scripts/sync_tracker.py`) serve as deterministic data processing, scoring, and formatting tools.
  - Tier 3 LinkedIn verification follows the strict safety envelope (jittered scrolling, max 30–50 views/day, 15m active / 20m cool-down).

---

## 4. Approaches Considered

### Approach A: Manual Spreadsheet & Ad-hoc Agent Prompts (Current Baseline)
- **Description:** Maintain Excel sheets and prompt an AI agent occasionally to read them and suggest roles.
- **Trade-offs:** Error-prone, fragmented, high manual effort, no automated alerts, easy to go stale.
- **Why Rejected:** Does not fulfill the user's intent of autonomous weekly assistance.

### Approach B: Heavy SaaS / 3rd-Party Scraper Integration (e.g. Apify, PhantomBuster)
- **Description:** Pay for external scraping APIs and webhooks.
- **Trade-offs:** Adds external subscription costs, complex API keys, and maintenance overhead.
- **Why Rejected:** Overkill when Google dorking and direct ATS endpoints provide 95% of target data cleanly and free of charge.

### Approach C: Lightweight Python Engine + Native Gmail + Multi-Tier Discovery (Selected)
- **Description:** 
  - Standardized local JSON data store with auto-generated Markdown view.
  - Multi-tier Python discovery script (`scripts/search_engine.py`) using search dorking + direct ATS queries + safe LinkedIn browser inspection.
  - Scoring engine (`scripts/scorer.py`) evaluating fit scores (1–5).
  - Weekly HTML email dispatcher using native `gmail` CLI tool.
  - Automation schedule configured for weekly delivery.
- **Why Chosen:** Zero external paid dependencies, utilizes existing authenticated Gmail tool, highly transparent, easy to test, and safest for LinkedIn.

---

## 5. System Architecture & Directory Layout

```
.
├── GEMINI.md                           # Agent operating manual & search rules
├── README.md                           # Operator manual & runbook
├── profile/
│   ├── candidate.json                  # Mansi's structured skills, criteria, & targets
│   └── Mansi_Agrawal_Resume.pdf        # Candidate resume
├── data/
│   ├── target_companies.json           # 60+ aerospace OEMs & startups (URLs, ATS type, tiers)
│   ├── openings.json                   # Live opportunities tracker (JSON)
│   └── Openings_Tracker.md             # Synchronized human-readable Markdown tracker
├── scripts/
│   ├── __init__.py
│   ├── search_engine.py                # Multi-tier job discovery runner
│   ├── scorer.py                       # Relevance & fit scoring engine (1-5)
│   ├── notifier.py                     # HTML digest generator & Gmail dispatch
│   └── sync_tracker.py                 # Syncs openings.json <-> Openings_Tracker.md
├── reports/                            # Generated weekly reports archive (YYYY-MM-DD.md / .html)
├── tests/
│   ├── test_scorer.py                  # Unit tests for scoring rules
│   └── test_notifier.py                # Unit tests for email generation
└── archive/
    ├── legacy_excel/                   # Preserved original .xlsx workbooks
    └── legacy_docs/                    # Preserved original .docx files
```

---

## 6. Data Schemas

### `profile/candidate.json`
```json
{
  "name": "Mansi Agrawal",
  "email": "agrawal.mansi20@gmail.com",
  "location": "Bangalore, India",
  "current_title": "Lead Systems Engineer",
  "experience_years": 10,
  "education": "MS Aerospace Engineering, Georgia Tech",
  "target_titles": [
    "MBSE Lead Engineer",
    "Lead Systems Engineer",
    "Systems Architecture Manager",
    "Avionics Lead Engineer",
    "V&V Lead",
    "Digital Engineering Lead"
  ],
  "core_skills": [
    "MBSE", "SysML", "Cameo", "MagicDraw", "IBM DOORS", 
    "3DEXPERIENCE", "ARP4754A", "ARP4761", "DO-178C", "DO-254",
    "ConOps", "Digital Thread", "MATLAB", "Simulink", "V&V"
  ],
  "target_domains": [
    "Commercial Aircraft", "UAV", "eVTOL", "Spacetech", "Defense Aerospace"
  ],
  "excluded_keywords": [
    "Frontend", "Backend", "Fullstack", "Web Developer", "Intern", 
    "Fresher", "Apprentice", "React", "Node.js"
  ]
}
```

### `data/openings.json` Entry Schema
```json
{
  "id": "AIRBUS-JR10400715",
  "company": "Airbus India",
  "team": "Digital / Systems Engineering",
  "title": "MBSE Capability Verification & Validation Leader",
  "location": "Bangalore",
  "req_id": "JR10400715",
  "seniority": "Manager/Lead",
  "fit_score": 5,
  "fit_rationale": "Direct MBSE V&V leadership in Bangalore commercial aircraft domain.",
  "skills_matched": ["MBSE", "V&V", "Systems Engineering"],
  "apply_url": "https://ag.wd3.myworkdayjobs.com/en-US/Airbus/job/Bangalore-Area/MBSE-Capability-Verification---Validation-Leader_JR10400715-1",
  "source": "Official (Workday)",
  "status": "Not Applied",
  "date_discovered": "2026-09-22",
  "last_updated": "2026-11-24",
  "next_action": "Draft tailored resume + cover note"
}
```

---

## 7. What is Left to the Builder

- Implementing the parser for legacy markdown and Excel rows into `target_companies.json` and `openings.json`.
- Writing the search query generators for Tier 1 Google Dorking and public ATS queries.
- Writing the HTML email template with styling suitable for both desktop and mobile email clients.
- Writing pytest unit tests to verify scoring accuracy and tracker sync.
