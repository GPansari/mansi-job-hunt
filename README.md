# Mansi Job Hunt Engine 🚀

> **Autonomous Aerospace Systems Engineering Job Hunting Command Center**  
> Tailored for **Mansi Agrawal** (Lead Systems Engineer, Boeing India | MS Aerospace, Georgia Tech | 10+ yrs MBSE & Systems Engineering)  
> Managed by **Gaurav Pansari** (`imgauravpansari@gmail.com`)  
> Target Recipient: **Mansi Agrawal** (`agrawal.mansi20@gmail.com`)  

---

## 1. Overview & Architecture

The **Mansi Job Hunt Engine** is an agent-orchestrated job hunting platform built specifically for high-seniority Aerospace Systems Engineering and MBSE opportunities in Bangalore, India. 

It solves the friction of manual job board browsing by combining:
1. **Multi-tier discovery**: Zero-bot-risk Google Dorking for public listings, direct ATS JSON monitoring (Workday, Greenhouse, Lever, Ashby) across 60+ aerospace companies, and safe LinkedIn inspection rules.
2. **Deterministic fit scoring (1–5)**: Evaluates roles against Mansi's specific proficiencies (Cameo, SysML, DOORS, 3DEXPERIENCE, ARP4754A, V&V, Avionics) while filtering negative keywords (interns, freshers, web devs).
3. **Dual-tracker synchronization**: Canonical JSON (`data/openings.json`) kept strictly in sync with a human-readable GitHub-flavored Markdown tracker (`data/Openings_Tracker.md`).
4. **Weekly curated digests**: Mobile-responsive HTML and plain-text executive summaries dispatched directly via the native Gmail CLI integration with strict deduplication and delivery gates.
5. **Phase 2 Application Tailoring & Interview Coaching**: Dossier-grounded JD alignment analysis, tailored resume/cover letter HTML & PDF generation, automated fact-checking audit gates, role-specific interview prep packs, and cross-role upskill summaries.

### System Data Flow

```
+---------------------------+        +-------------------------------+
|  profile/candidate.json   |        |   data/target_companies.json  |
|  (Mansi's Skills & Target)|        |   (60+ Aerospace OEMs/Startups|
+-------------+-------------+        +---------------+---------------+
              |                                      |
              v                                      v
       +----------------------------------------------------+
       |          scripts/search_engine.py                  |
       |  • Tier 1: Google Dorking Queries                  |
       |  • Tier 2: Public ATS APIs (Workday/Greenhouse/etc)|
       |  • Tier 3: Safe LinkedIn Inspection Guidelines     |
       +-------------------------+--------------------------+
                                 |
                                 v
       +----------------------------------------------------+
       |               scripts/scorer.py                    |
       |  • Evaluates Fit Score (1 to 5)                    |
       |  • Matches Core Skills & Domain Keywords           |
       |  • Enforces Disqualification Gates                 |
       +-------------------------+--------------------------+
                                 |
                                 v
       +----------------------------------------------------+
       |             Dual-Tracker Data Layer                |
       |  • data/openings.json (Single Source of Truth)     |
       |  • data/Openings_Tracker.md (Markdown Table)       |
       |  • scripts/sync_tracker.py (Bi-directional Sync)   |
       +-------------------------+--------------------------+
                                 |
                                 v
       +----------------------------------------------------+
       |              scripts/notifier.py                   |
       |  • Deduplication Gate (reports/sent_history.json)  |
       |  • Minimum Fit Gate (fit_score >= 3.0)             |
       |  • Compiles Executive Plain-Text & HTML Digest     |
       |  • Dispatches via Gmail CLI (or --dry-run preview) |
       +-------------------------+--------------------------+
                                 |
                                 v
                  Mansi's Inbox: agrawal.mansi20@gmail.com
```

---

## 2. Directory Map

```
.
├── GEMINI.md                           # AI Agent operating manual, constitution & SOP
├── README.md                           # Operator manual, runbook, & architecture guide
├── pyproject.toml                      # Python package & pytest configuration
├── .agents/
│   └── skills/
│       └── job-application-coach/
│           └── SKILL.md                # Antigravity Phase 2 coaching skill (/apply, /review-app, /interview, /upskill)
├── profile/
│   ├── candidate.json                  # Candidate profile (skills, target titles, locations)
│   ├── master_dossier.md               # Verified master dossier (roles, metrics, tools, standards)
│   └── Mansi_Agrawal_Resume.pdf        # Mansi's aerospace resume
├── templates/
│   ├── resume.html                     # Print-ready HTML/CSS template for tailored resumes
│   └── cover_letter.html               # Print-ready HTML/CSS template for tailored cover letters
├── applications/                       # Gitignored local per-role packages (analysis, PDFs, review, interview prep)
├── data/
│   ├── target_companies.json           # 60+ aerospace companies, portals, ATS types & tiers
│   ├── openings.json                   # Canonical opportunities tracker (JSON)
│   └── Openings_Tracker.md             # Human-readable Markdown tracker table
├── docs/
│   └── index.html                      # Live single-page review portal (GitHub Pages)
├── scripts/
│   ├── __init__.py
│   ├── generate_site.py                # Static web portal builder for GitHub Pages
│   ├── verify_links.py                 # Live HTTP link health & ATS expiration auditor
│   ├── search_engine.py                # Multi-tier job search & ATS ingestion engine
│   ├── scorer.py                       # Candidate fit & relevance scoring engine
│   ├── notifier.py                     # Weekly digest compiler & Gmail dispatcher
│   ├── sync_tracker.py                 # Bi-directional JSON <-> Markdown synchronizer
│   ├── profile_loader.py               # Verified master dossier & candidate profile loader
│   ├── jd_analyzer.py                  # Deep JD alignment analyzer & gap detector
│   ├── application_builder.py          # Tailored resume, cover letter, & Chrome PDF builder
│   ├── application_reviewer.py         # Fact-checking reviewer & ATS/page-budget audit gate
│   ├── interview_prep.py               # Grounded per-role interview preparation pack builder
│   └── upskill_analyzer.py             # Cross-role skill gap & upskill report generator
├── reports/
│   ├── sent_history.json               # Deduplication ledger tracking notified role IDs
│   ├── upskill_summary.md              # Cross-role recurring skill gap & upskill summary
│   └── *.html / *.txt                  # Timestamped archive copies of weekly digests
├── tests/                              # Comprehensive test suite (unit + integration)
│   ├── test_data_integrity.py          # Validates schema structure & data migrations
│   ├── test_sync_tracker.py            # Tests round-trip Markdown/JSON sync
│   ├── test_scorer.py                  # Tests scoring rubric & negative keyword filters
│   ├── test_notifier.py                # Tests digest formatting & email dispatching
│   ├── test_search_engine.py           # Tests ATS APIs, dorking, & deduplication
│   ├── test_runbook.py                 # Tests CLI workflows & runbook end-to-end
│   ├── test_profile_loader.py          # Tests master dossier & PDF extraction loader
│   ├── test_jd_analyzer.py             # Tests JD fetching, LinkedIn block, & gap analysis
│   ├── test_application_builder.py     # Tests tailored resume/cover letter & PDF generation
│   ├── test_application_reviewer.py    # Tests fact-check audit, placeholders, & page budget
│   └── test_interview_and_upskill.py   # Tests interview prep & cross-role upskill analyzer
└── archive/
    ├── legacy_excel/                   # Preserved original Excel spreadsheets
    └── legacy_docs/                    # Preserved original Word documents
```

---

## 3. Quick Start

### Prerequisites
- **Python 3.10+** (standard library only; zero heavy third-party runtime dependencies).
- **Pytest** (`pip install pytest` or installed in virtualenv).
- **Gmail Plugin** (configured in Antigravity or `imgauravpansari@gmail.com` logged in).

### Verification
Run the complete test suite to confirm data integrity and engine functions:
```bash
pytest -v
```

All 110+ tests should pass out of the box.

---

## 4. Running CLI Scripts

### 1. Opportunity Discovery (`scripts/search_engine.py`)

Generate Google Dorking queries for safe web search:
```bash
python scripts/search_engine.py --queries
```

Scan target company ATS feeds (Workday, Greenhouse, Lever, Ashby) and preview matches:
```bash
python scripts/search_engine.py --scan-ats
```

Scan ATS feeds and automatically ingest passing roles (`fit_score >= 3`) into `data/openings.json` and sync `data/Openings_Tracker.md`:
```bash
python scripts/search_engine.py --scan-ats --ingest-new
```

Filter scan by specific company:
```bash
python scripts/search_engine.py --scan-ats --company Airbus
```

Preview without saving:
```bash
python scripts/search_engine.py --scan-ats --dry-run
```

---

### 2. Candidate Fit Scoring (`scripts/scorer.py`)

Score a single job opening payload from JSON:
```bash
python scripts/scorer.py --job-json '{"title": "MBSE Leader", "company": "Airbus", "location": "Bangalore"}'
```

Batch re-score all openings in `data/openings.json` and update scores:
```bash
python scripts/scorer.py --score-all
```

---

### 3. Dual-Tracker Synchronization (`scripts/sync_tracker.py`)

Sync canonical JSON to Markdown tracker (standard after discovery or scoring updates):
```bash
python scripts/sync_tracker.py --to-md
```

Sync manual edits in Markdown tracker back into JSON (e.g. status changes, notes):
```bash
python scripts/sync_tracker.py --to-json
```

Verify live posting links and regenerate the static GitHub Pages review portal:
```bash
python scripts/verify_links.py
python scripts/generate_site.py
```

---

### 4. Weekly Digest Generator & Dispatcher (`scripts/notifier.py`)

Preview weekly digest in terminal without sending an email (**Dry Run**):
```bash
python scripts/notifier.py --dry-run
```

Dispatch digest email directly to Mansi (`agrawal.mansi20@gmail.com`) via Gmail CLI:
```bash
python scripts/notifier.py --send
```

Include all roles, ignoring previously sent history (useful for testing or resending):
```bash
python scripts/notifier.py --dry-run --all
```

Specify a custom minimum fit threshold (e.g. top-tier only):
```bash
python scripts/notifier.py --dry-run --min-fit 4.0
```

---

### 5. Phase 2: JD Analysis & Application Tailoring (`scripts/jd_analyzer.py`, `scripts/application_builder.py`)

Analyze a shortlisted opening against `profile/master_dossier.md` (writes `applications/<id>/analysis.{json,md}`):
```bash
# Fetch from a non-LinkedIn public ATS URL:
python scripts/jd_analyzer.py --id AIRBUS-JR10437140 --fetch

# Or pass a local JD file / pasted text (required for LinkedIn postings):
python scripts/jd_analyzer.py --id AIRBUS-JR10437140 --jd-file path/to/jd.txt
```

Build a tailored resume, cover letter, and print-ready PDFs under `applications/<id>/` (add `--no-pdf` to skip headless Google Chrome PDF compilation):
```bash
python scripts/application_builder.py --id AIRBUS-JR10437140
python scripts/application_builder.py --id AIRBUS-JR10437140 --no-pdf
```

---

### 6. Phase 2: Fact-Checking Audit Gate (`scripts/application_reviewer.py`)

Verify contact fidelity, dossier-only claims, absence of placeholders, ATS keyword coverage, and `<= 2` page resume PDF budget (`applications/<id>/review.{json,md}`):
```bash
python scripts/application_reviewer.py --id AIRBUS-JR10437140
```

---

### 7. Phase 2: Interview Prep & Cross-Role Upskill Summary (`scripts/interview_prep.py`, `scripts/upskill_analyzer.py`)

Generate a role-specific interview prep pack (`applications/<id>/interview_prep.md`):
```bash
python scripts/interview_prep.py --id AIRBUS-JR10437140
```

Aggregate recurring `skill_gaps` and `missing_standards` across all evaluated roles into `reports/upskill_summary.md`:
```bash
python scripts/upskill_analyzer.py --output reports/upskill_summary.md
```

---

## 5. Human Operator & Maintenance Workflows

### Updating Application Status
When Mansi applies for a role or receives an update:
1. Open [`data/Openings_Tracker.md`](file:///Users/gp/Desktop/GP%20Github%20Local/Mansi%20Job%20Hunt/data/Openings_Tracker.md).
2. Update the `Status` column (e.g. `Applied`, `Interviewing`, `Offer`, `Rejected`) and `Next Action`.
3. Run the sync command to persist changes to the canonical JSON:
   ```bash
   python scripts/sync_tracker.py --to-json
   ```

### Adding New Target Companies
1. Open [`data/target_companies.json`](file:///Users/gp/Desktop/GP%20Github%20Local/Mansi%20Job%20Hunt/data/target_companies.json).
2. Append a new company entry:
   ```json
   {
     "name": "Supernal",
     "category": "eVTOL / Urban Air Mobility",
     "relevance": 5,
     "careers_url": "https://jobs.lever.co/supernal",
     "ats_type": "lever",
     "tier": "Startup / NewSpace"
   }
   ```
3. Run `python scripts/search_engine.py --scan-ats --company Supernal` to verify.

### Updating Candidate Skills & Criteria
Edit [`profile/candidate.json`](file:///Users/gp/Desktop/GP%20Github%20Local/Mansi%20Job%20Hunt/profile/candidate.json) to add newly acquired certifications, tools, or target domains, and keep [`profile/master_dossier.md`](file:///Users/gp/Desktop/GP%20Github%20Local/Mansi%20Job%20Hunt/profile/master_dossier.md) updated with verified achievements so Phase 2 tailored resumes and interview prep packs stay current. Re-run scoring with `python scripts/scorer.py --score-all` followed by `python scripts/sync_tracker.py --to-md`.

---

## 6. Safety Envelope & Anti-Bot Limits

The engine enforces strict human-mimicking constraints to protect LinkedIn accounts:
- **Scroll step**: 250–600 px jittered scroll chunks.
- **Action pause**: 2–6 seconds random delays between interactions.
- **Daily cap**: Maximum 30–50 views per day.
- **Duty cycle**: 15 minutes browsing followed by 20 minutes cool-down.

For autonomous agent operation rules and slash command specifications, see [`GEMINI.md`](file:///Users/gp/Desktop/GP%20Github%20Local/Mansi%20Job%20Hunt/GEMINI.md).
