# GEMINI.md - Agent Operating Manual & Constitution

> **Autonomous Job Hunt Engine for Mansi Agrawal**  
> **Repository:** `Mansi Job Hunt`  
> **Version:** 2.0 (Agent-Orchestrated)  
> **Primary Operator:** Gaurav Pansari (`imgauravpansari@gmail.com`)  
> **Target Candidate:** Mansi Agrawal (`agrawal.mansi20@gmail.com`)  

---

## 1. Candidate Profile Overview

AI agents operating in this repository must align all discovery, scoring, and recommendation decisions with Mansi Agrawal's candidate profile:

| Attribute | Details |
|---|---|
| **Candidate Name** | Mansi Agrawal |
| **Current Role** | Lead Systems Engineer @ Boeing India (Bangalore) |
| **Experience** | 10+ years in Aerospace Systems Engineering, Digital Engineering, and MBSE |
| **Education** | Master of Science (MS) in Aerospace Engineering, Georgia Institute of Technology (Georgia Tech) |
| **Location Target** | Bangalore / Bengaluru, Karnataka, India (Remote/Hybrid acceptable for select global aerospace programs) |
| **Target Industries** | Commercial Aviation, Defense Aerospace, UAVs / Unmanned Systems, eVTOL / Advanced Air Mobility, Spacetech |
| **Core Technical Skills** | Model-Based Systems Engineering (MBSE), Cameo Systems Modeler, MagicDraw, SysML (v1 & v2), IBM DOORS / DOORS Next Generation (DNG), 3DEXPERIENCE, ARP4754A, ARP4761, DO-178C, DO-254, Concept of Operations (ConOps), Digital Thread, MATLAB / Simulink, Systems Architecture, Requirements Management, Verification & Validation (V&V), Avionics Protocols (ARINC 429, AFDX) |
| **Target Seniority** | Lead Engineer, Staff Systems Engineer, Principal Systems Engineer, Systems Engineering Manager, MBSE Capability Lead, V&V Lead |
| **Disqualified Keywords** | Intern, Fresher, Apprentice, Graduate Trainee, Frontend, Backend, Fullstack, React, Node.js, Web Developer |

Candidate canonical profile source: [`profile/candidate.json`](file:///Users/gp/Desktop/GP%20Github%20Local/Mansi%20Job%20Hunt/profile/candidate.json).

---

## 2. Core Operating Rules & Non-Negotiables

Every autonomous agent working in this repository must strictly adhere to these fundamental laws:

1. **Canonical JSON as Single Source of Truth**:
   - `data/openings.json` is the sole authoritative record for all tracked job opportunities.
   - `data/target_companies.json` is the authoritative registry of aerospace OEMs, tier-1 suppliers, and startups.
   - `profile/candidate.json` defines candidate skills, target criteria, and exclusions.

2. **Mandatory Dual-Tracker Synchronization**:
   - Whenever `data/openings.json` is modified (added, updated, deleted), immediately regenerate `data/Openings_Tracker.md` using:
     ```bash
     python scripts/sync_tracker.py --to-md
     ```
   - Never allow `data/openings.json` and `data/Openings_Tracker.md` to drift out of sync.
   - If manual edits are made directly to `data/Openings_Tracker.md` (e.g. updating application status or next steps), sync back to JSON using:
     ```bash
     python scripts/sync_tracker.py --to-json
     ```

3. **Strict Gate Threshold (`fit_score >= 3.0`)**:
   - Only opportunities with a calculated `fit_score >= 3.0` and `passed_gate == True` may be ingested into active tracking or included in notification digests.
   - Any role containing negative keywords ("intern", "fresher", "web developer", etc.) is automatically disqualified with `passed_gate = False` regardless of score.

4. **Rigorous Deduplication**:
   - Every opportunity must be checked for duplicates before ingestion.
   - Duplicate criteria: identical `id` (e.g., `AIRBUS-JR10400715`), matching `req_id`, or normalized `apply_url`.

5. **Zero-Spam & Delivery Failsafes**:
   - Never re-notify Mansi about a role already dispatched in a previous digest.
   - All sent role IDs are immutably logged in `reports/sent_history.json`.
   - Every email digest is permanently archived in `reports/YYYY-MM-DD-digest.html` and `.txt`.

6. **Human-in-the-Loop for Submissions**:
   - The engine discovers, scores, verifies, tracks, and compiles digests.
   - The agent **must never** submit applications or contact recruiters on Mansi's behalf without explicit human instruction.

7. **Requisition-Specific Links Only (No Generic Career Portals)**:
   - Every `apply_url` in `data/openings.json` must resolve directly to the specific job requisition (e.g. Workday job detail page, direct Lever/Greenhouse/Freshteam/Kula post, or direct LinkedIn job view).
   - Generic company careers homepages (e.g., `company.com/careers`) are strictly prohibited in the tracker.

8. **Inactive Posting Lifecycle & Status Preservation**:
   - Roles confirmed closed or expired must be tagged with `status: "Inactive Posting"` and annotated with explanation in `next_action`. They are never left as active or silently deleted.

---

## 3. LinkedIn Safety Envelope & Scraping Guardrails

When inspecting LinkedIn job postings, agents and browser automation tools **must strictly obey** the following human-mimicking safety constraints to prevent anti-bot challenges (HTTP 999, CAPTCHAs, or account restrictions):

```
+--------------------------------------------------------------------------+
|                        LINKEDIN SAFETY ENVELOPE                          |
+--------------------------------------------------------------------------+
| Scroll Behavior : Non-linear, jittered scrolls in 250 - 600 px chunks    |
| Inter-Action Pause: Random 2 - 6 second pauses between clicks/views      |
| Daily View Cap  : Maximum 30 - 50 job/profile views per 24-hour window   |
| Duty Cycle      : Max 15 minutes continuous active browsing              |
| Cool-Down Period: Mandatory 20 minutes idle after each active session    |
+--------------------------------------------------------------------------+
```

### Operational Guidance:
- **Tier 1 First**: Always favor Google Dorking (`site:linkedin.com/jobs/view ...`) or search engine indexing over direct LinkedIn portal browsing.
- **Tier 2 Public ATS First**: Query public Workday, Greenhouse, Lever, and Ashby endpoints before touching LinkedIn.
- If an anti-bot or CAPTCHA screen is encountered: **STOP IMMEDIATELY**. Do not attempt to bypass or solve it. Record the URL for manual human verification.

---

## 4. Agent Command Workflows (Slash Commands)

Agents should recognize and execute the following standard operational workflows:

### `/discover` - Multi-Tier Opportunity Discovery
Discovers new job openings across Google Dorking queries and public ATS feeds, scores them, and ingests passing roles.

```bash
# 1. Generate Google Dorking search strings for web research
python scripts/search_engine.py --queries

# 2. Query configured public ATS feeds and automatically ingest high-fit roles
python scripts/search_engine.py --scan-ats --ingest-new

# 3. Synchronize Markdown tracker
python scripts/sync_tracker.py --to-md
```

**Agent Execution Steps**:
1. Run `python scripts/search_engine.py --queries` and conduct targeted web searches using `search_web` for top dorking strings.
2. Run `python scripts/search_engine.py --scan-ats --ingest-new` to query live Workday, Greenhouse, Lever, and Ashby endpoints for target companies.
3. For any external web search hit: score via `scripts/scorer.py` and append to `data/openings.json` if `fit_score >= 3.0`.
4. Ensure `data/Openings_Tracker.md` is updated.
5. Report the number of newly discovered roles and their fit breakdown to the user.

---

### `/sync` - Dual Tracker Synchronization
Synchronizes the canonical JSON tracker and the human-readable Markdown table.

```bash
# Sync JSON to Markdown (default after data ingest)
python scripts/sync_tracker.py --to-md

# Sync Markdown to JSON (if human edited Openings_Tracker.md)
python scripts/sync_tracker.py --to-json
```

**Agent Execution Steps**:
1. Check file modification timestamps of `data/openings.json` and `data/Openings_Tracker.md`.
2. Run appropriate sync flag (`--to-md` or `--to-json`).
3. Validate table formatting, header integrity, and link validity.

---

### `/digest` - Weekly Digest Preview (Dry Run)
Compiles the weekly executive summary of unnotified high-fit roles and renders a terminal preview without sending an email.

```bash
python scripts/notifier.py --dry-run
```

**Agent Execution Steps**:
1. Loads `data/openings.json` and excludes roles already logged in `reports/sent_history.json`.
2. Filters roles where `fit_score >= 3.0`.
3. Displays the structured plain-text digest, match counts by fit level (5/5, 4/5, 3/5), and requisition details.
4. Confirms that no email was sent and no history was modified.

---

### `/email` - Direct Weekly Gmail Dispatch
Dispatches the curated HTML and plain-text digest to Mansi Agrawal via the authenticated Gmail plugin.

```bash
python scripts/notifier.py --send
```

**Agent Execution Steps**:
1. Validates recipient (`agrawal.mansi20@gmail.com`) and sender (`imgauravpansari@gmail.com`).
2. Generates responsive executive HTML and fallback plain-text bodies.
3. Dispatches via `gmail mutate send`.
4. Appends dispatched role IDs to `reports/sent_history.json`.
5. Archives timestamped copy to `reports/YYYY-MM-DD-digest.html` and `.txt`.
6. Summarizes dispatch confirmation and role count to the operator.

---

## 5. Weekly Automation Schedule Configuration

To run this pipeline autonomously each week using Antigravity's native scheduling system:

### Recommended Cadence
- **Trigger**: Every Monday at **09:00 AM IST** (`03:30 AM UTC`).
- **Cron Expression**: `30 3 * * 1`

### Scheduling via Slash Command / Prompt
Instruct Antigravity in chat or via the `/schedule` slash command:
```
/schedule CronExpression="30 3 * * 1" Prompt="Execute weekly job hunt pipeline: run /discover, synchronize trackers, and dispatch weekly digest to agrawal.mansi20@gmail.com via scripts/notifier.py --send."
```

### Automated Pipeline Flow
When triggered on schedule, the agent performs the following sequential runbook:
1. **ATS Discovery**: Execute `python scripts/search_engine.py --scan-ats --ingest-new`.
2. **Search Verification**: Check generated queries for newly posted roles in the past 7 days.
3. **Tracker Sync**: Run `python scripts/sync_tracker.py --to-md`.
4. **Digest Verification**: Run `python scripts/notifier.py --dry-run` to inspect unnotified candidate count.
5. **Conditional Dispatch**:
   - If unnotified roles &ge; 1: Execute `python scripts/notifier.py --send`.
   - If unnotified roles == 0: Log `"No new unnotified roles this week - skipping email dispatch."`
6. **Status Report**: Output a concise run log with matched roles, score breakdown, and archive links.

---

## 6. Directory Layout & Key File Map

```
.
├── GEMINI.md                           # This operating manual & agent constitution
├── README.md                           # Operator guide, runbook, & setup instructions
├── docs/
│   └── index.html                      # Live single-page review portal (GitHub Pages)
├── profile/
│   ├── candidate.json                  # Mansi's structured skills, criteria, & targets
│   └── Mansi_Agrawal_Resume.pdf        # Candidate resume
├── data/
│   ├── target_companies.json           # 60+ aerospace OEMs & startups (URLs, ATS type, tiers)
│   ├── openings.json                   # Live opportunities tracker (canonical JSON)
│   └── Openings_Tracker.md             # Synchronized human-readable Markdown tracker
├── scripts/
│   ├── __init__.py
│   ├── generate_site.py                # Static web portal builder for GitHub Pages
│   ├── verify_links.py                 # Live HTTP link health & ATS expiration auditor
│   ├── search_engine.py                # Multi-tier discovery runner (Dorking + ATS)
│   ├── scorer.py                       # Relevance & fit scoring engine (1-5)
│   ├── notifier.py                     # HTML digest generator & Gmail dispatch
│   └── sync_tracker.py                 # Bi-directional tracker synchronizer
├── reports/                            # Generated weekly reports archive & sent history
│   └── sent_history.json               # Deduplication ledger of already-notified role IDs
├── tests/                              # Pytest test suite
│   ├── test_data_integrity.py
│   ├── test_generate_site.py
│   ├── test_sync_tracker.py
│   ├── test_scorer.py
│   ├── test_notifier.py
│   ├── test_search_engine.py
│   └── test_runbook.py
└── archive/
    ├── legacy_excel/                   # Preserved original .xlsx workbooks
    └── legacy_docs/                    # Preserved original .docx files
```

---

## 7. Troubleshooting & Recovery Procedures

- **ATS Endpoint Changes / Timeouts**:
  `scripts/search_engine.py` is resilient to 404/500 errors and network timeouts. If a company changes its careers portal URL, update the `careers_url` and `ats_type` in `data/target_companies.json`.
- **Accidental Deletion of Openings**:
  If `data/openings.json` is corrupted or lost, recover historical records from `data/Openings_Tracker.md` using `python scripts/sync_tracker.py --to-json` or revert via git.
- **Gmail Authorization Reconnect**:
  If `gmail` CLI reports authentication expired, instruct the operator to reconnect the Gmail account in the Antigravity Plugins Manager.
- **Resending a Digest**:
  To re-include previously sent roles in a digest preview, use `python scripts/notifier.py --dry-run --all`.

---

## 8. Captured Operational Learnings & Platform Quirks

During the build and execution cycles, several critical operational insights were codified:

1. **Workday CXS API Mechanics & Anti-Scraping Defenses**:
   - Workday portals (e.g. `ag.wd3.myworkdayjobs.com`, `globalhr.wd5.myworkdayjobs.com`, `boeing.wd1.myworkdayjobs.com`) protect their HTML endpoints against basic scripts.
   - Hitting Workday via Python standard `urllib` without custom headers triggers `HTTP 429` rate limiting.
   - Reliable programmatic access uses direct POST to the Workday CXS search endpoint (`https://<domain>/wday/cxs/<tenant>/<site>/jobs`) with custom `User-Agent` and `Accept: application/json` headers, returning full structured pagination and req IDs.
   - Direct job URLs follow the pattern: `https://<domain>/en-US/<site>/job/<location-slug>/<title-slug>_<req_id>`.

2. **LinkedIn Safety & Dorking Superiority**:
   - Direct automated browsing on LinkedIn easily triggers anti-bot checkpoints (HTTP 999 or CAPTCHA).
   - Google Dorking with specific search terms (`site:in.linkedin.com/jobs/view ...`) or querying public ATS indices surfaces live, indexed requisitions without hitting LinkedIn account rate limits.
   - When inspecting LinkedIn URLs, agents must maintain human-mimicking pacing (250–600px non-linear scrolls, 2–6s pauses, max 30–50 views/day, 15m duty cycle).

3. **Gmail Dispatch & CLI Options**:
   - The Antigravity Gmail CLI expects `--body-file <path> --html` for sending rich HTML emails.
   - In sandboxed runtime environments, the initial CLI binary installation requires a one-time elevated execution (`BypassSandbox: true`).
   - Dynamic role fields must always be escaped with `html.escape(..., quote=True)` to prevent broken rendering on titles containing ampersands (`&`).

4. **Dual-Tracker Consistency**:
   - `data/openings.json` is the canonical programmatic store; `data/Openings_Tracker.md` is the human-facing view.
   - Whenever any script modifies `data/openings.json`, immediately run `python scripts/sync_tracker.py --to-md` to prevent sync drift.
   - Web review portal is rebuilt using `python scripts/generate_site.py`.
