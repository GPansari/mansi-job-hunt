# Autonomous Job Hunt Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Mansi Job Hunt workspace into a best-in-class, agent-orchestrated job hunting system with clean data schemas, multi-tier discovery tools, fit scoring, tracker synchronization, and direct weekly Gmail alerts to Mansi.

**Architecture:** A single source of truth in JSON (`profile/candidate.json`, `data/target_companies.json`, `data/openings.json`) synchronized with a human-readable Markdown tracker (`data/Openings_Tracker.md`). Modular Python engines provide ATS queries, fit scoring, sync, and HTML email compilation dispatched via the native Gmail integration under an agent-orchestrated schedule governed by `GEMINI.md`.

**Tech Stack:** Python 3 (standard library, `pytest`), Gmail CLI plugin (`gmail`), Markdown, JSON.

**Spec:** `docs/superpowers/specs/2026-11-24-job-hunt-engine-design.md`

## Global Constraints

- Recipient email: `agrawal.mansi20@gmail.com`
- Sender account: `imgauravpansari@gmail.com` (connected via Gmail plugin)
- Email mode: Direct Send with fail-safe gates (duplicate prevention, `fit_score >= 3`, URL validation)
- LinkedIn Safety Envelope: 250–600px non-linear scroll chunks, 2–6s pauses, max 30–50 views/day, 15m on / 20m off duty cycle
- Zero external paid APIs or fragile headless browser scrapers; Tier 1 discovery uses Google Dorking and public ATS feeds
- All legacy files (`.xlsx`, `.docx`) preserved in `archive/`

## Review Focus

1. Duplicate email prevention: Role IDs already sent in previous reports must never appear in subsequent digests.
2. Low-relevance exclusion: Roles below Fit Score 3 or matching excluded keywords (e.g. "intern", "apprentice", "fresher", "web developer") must be filtered out.
3. Bidirectional Markdown-JSON sync: Modifications to `openings.json` must generate valid GitHub-flavored Markdown in `Openings_Tracker.md` without dropping columns or links.
4. Missing or malformed data resilience: Openings with missing Req IDs, unverified links, or empty skill fields must not crash scoring or email compilation.
5. Email format responsiveness: Digest HTML must render cleanly across mobile and desktop mail clients with fallback plain text / Markdown.

---

### Task 1: Repository Reorganization & Data Migration

**Files:**
- Create: `profile/candidate.json`
- Create: `data/target_companies.json`
- Create: `data/openings.json`
- Move: `Mansi Agrawal Resume.pdf` -> `profile/Mansi_Agrawal_Resume.pdf`
- Move: `*.xlsx` -> `archive/legacy_excel/`
- Move: `Target Companies.docx` -> `archive/legacy_docs/`
- Test: `tests/test_data_integrity.py`

**Interfaces:**
- Produces: Valid JSON files for candidate, target companies, and active openings matching Section 6 of the design spec.

- [ ] **Step 1: Write test for initial data integrity**

```python
# tests/test_data_integrity.py
import json
from pathlib import Path

def test_candidate_profile_schema():
    candidate_file = Path("profile/candidate.json")
    assert candidate_file.exists()
    data = json.loads(candidate_file.read_text())
    assert data["name"] == "Mansi Agrawal"
    assert data["email"] == "agrawal.mansi20@gmail.com"
    assert "MBSE" in data["core_skills"]
    assert len(data["target_titles"]) > 0

def test_target_companies_schema():
    companies_file = Path("data/target_companies.json")
    assert companies_file.exists()
    data = json.loads(companies_file.read_text())
    assert len(data) >= 20
    for company in data:
        assert "name" in company
        assert "relevance" in company
        assert "careers_url" in company

def test_openings_schema():
    openings_file = Path("data/openings.json")
    assert openings_file.exists()
    data = json.loads(openings_file.read_text())
    assert len(data) >= 10
    for op in data:
        assert "id" in op
        assert "company" in op
        assert "title" in op
        assert "fit_score" in op
        assert "status" in op
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_data_integrity.py -v`  
Expected: FAIL (files do not exist yet)

- [ ] **Step 3: Reorganize directories and migrate data**

1. Create directories: `profile/`, `data/`, `scripts/`, `reports/`, `tests/`, `archive/legacy_excel/`, `archive/legacy_docs/`.
2. Move legacy Excel workbooks and Word docs into `archive/`.
3. Move `Mansi Agrawal Resume.pdf` into `profile/`.
4. Generate `profile/candidate.json` with extracted resume data and target criteria.
5. Parse `Target Companies.md` into `data/target_companies.json`.
6. Parse `Openings Tracker.md` into `data/openings.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_data_integrity.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add profile/ data/ archive/ tests/
git commit -m "chore: reorganize repo structure and migrate data to canonical JSON schemas"
```

---

### Task 2: Dual Tracker Synchronization (`scripts/sync_tracker.py`)

**Files:**
- Create: `scripts/sync_tracker.py`
- Create: `data/Openings_Tracker.md`
- Test: `tests/test_sync_tracker.py`

**Interfaces:**
- Consumes: `data/openings.json`
- Produces: `sync_json_to_markdown(json_path: Path, md_path: Path) -> None`
- Produces: CLI `python scripts/sync_tracker.py [--to-md | --to-json]`

- [ ] **Step 1: Write test for tracker sync**

```python
# tests/test_sync_tracker.py
import json
from pathlib import Path
from scripts.sync_tracker import sync_json_to_markdown

def test_sync_json_to_markdown(tmp_path):
    json_file = tmp_path / "openings.json"
    md_file = tmp_path / "Openings_Tracker.md"
    sample = [{
        "id": "AIRBUS-1",
        "company": "Airbus India",
        "team": "Systems",
        "title": "MBSE Leader",
        "location": "Bangalore",
        "req_id": "JR100",
        "seniority": "Lead",
        "fit_score": 5,
        "fit_rationale": "Direct match",
        "skills_matched": ["MBSE"],
        "apply_url": "https://example.com",
        "source": "Workday",
        "status": "Not Applied",
        "date_discovered": "2026-11-24",
        "last_updated": "2026-11-24",
        "next_action": "Apply"
    }]
    json_file.write_text(json.dumps(sample))
    sync_json_to_markdown(json_file, md_file)
    content = md_file.read_text()
    assert "| Company | Team | Role | Location | Req ID | Seniority | Fit | Status | Link | Next Action |" in content
    assert "| Airbus India | Systems | MBSE Leader | Bangalore | JR100 | Lead | 5 | Not Applied | [Apply](https://example.com) | Apply |" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sync_tracker.py -v`  
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `scripts/sync_tracker.py`**

Implement `sync_json_to_markdown` formatting table columns cleanly and providing a CLI entrypoint.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_sync_tracker.py -v`  
Expected: PASS

- [ ] **Step 5: Synchronize real `data/Openings_Tracker.md` and commit**

```bash
python scripts/sync_tracker.py --to-md
git add scripts/sync_tracker.py data/Openings_Tracker.md tests/test_sync_tracker.py
git commit -m "feat: add bi-directional tracker sync utility"
```

---

### Task 3: Fit Scoring Engine (`scripts/scorer.py`)

**Files:**
- Create: `scripts/scorer.py`
- Test: `tests/test_scorer.py`

**Interfaces:**
- Consumes: `profile/candidate.json`
- Produces: `score_job(job_dict: dict, candidate_profile: dict) -> dict` returning `fit_score` (1-5), `skills_matched`, `fit_rationale`, and `passed_gate` (bool).

- [ ] **Step 1: Write test for scoring engine**

```python
# tests/test_scorer.py
from scripts.scorer import score_job

candidate = {
    "target_titles": ["Lead Systems Engineer", "MBSE Lead", "Avionics Lead"],
    "core_skills": ["MBSE", "SysML", "Cameo", "DOORS", "ARP4754A"],
    "target_locations": ["Bangalore", "Bengaluru"],
    "excluded_keywords": ["Intern", "Fresher", "Apprentice", "Frontend", "Fullstack"]
}

def test_high_fit_role():
    job = {
        "title": "MBSE Capability Verification & Validation Leader",
        "description": "Leading MBSE adoption using Cameo, SysML, and DOORS in Bangalore.",
        "location": "Bangalore"
    }
    result = score_job(job, candidate)
    assert result["fit_score"] >= 4
    assert "MBSE" in result["skills_matched"]
    assert "Cameo" in result["skills_matched"]
    assert result["passed_gate"] is True

def test_excluded_role_fails_gate():
    job = {
        "title": "Software Engineering Intern - Web Fullstack",
        "description": "React and Node.js intern in Bangalore.",
        "location": "Bangalore"
    }
    result = score_job(job, candidate)
    assert result["fit_score"] == 1
    assert result["passed_gate"] is False

def test_different_location_penalized():
    job = {
        "title": "Lead Systems Engineer",
        "description": "MBSE and SysML modeling.",
        "location": "Hyderabad"
    }
    result = score_job(job, candidate)
    assert result["fit_score"] <= 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scorer.py -v`  
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `scripts/scorer.py`**

Implement scoring rules:
- Excluded keyword check (instant 1 and `passed_gate = False`)
- Title match (+1.5 score)
- Skill keywords match (+0.5 per core skill, max +2.5)
- Location match (Bangalore: +1.0; other: -1.0)
- Clamped between 1 and 5. Gate passes if `fit_score >= 3` and no excluded keywords.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scorer.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/scorer.py tests/test_scorer.py
git commit -m "feat: implement job fit scoring engine"
```

---

### Task 4: Weekly Digest Generator & Gmail Dispatcher (`scripts/notifier.py`)

**Files:**
- Create: `scripts/notifier.py`
- Test: `tests/test_notifier.py`

**Interfaces:**
- Consumes: `data/openings.json`, `reports/sent_history.json`
- Produces: `generate_digest(openings: list, new_only: bool = True) -> tuple[str, str]` (returns text_body, html_body)
- Produces: `dispatch_email(recipient: str, subject: str, text_body: str, html_body: str, dry_run: bool = False) -> bool`

- [ ] **Step 1: Write test for email notifier**

```python
# tests/test_notifier.py
from scripts.notifier import generate_digest, filter_unnotified_roles

def test_filter_unnotified_roles():
    history = {"AIRBUS-JR10400715"}
    openings = [
        {"id": "AIRBUS-JR10400715", "fit_score": 5},
        {"id": "RTX-01868963", "fit_score": 5},
        {"id": "LOW-FIT-1", "fit_score": 2}
    ]
    unnotified = filter_unnotified_roles(openings, history, min_fit_score=3)
    assert len(unnotified) == 1
    assert unnotified[0]["id"] == "RTX-01868963"

def test_generate_digest_content():
    roles = [{
        "id": "RTX-01868963",
        "company": "Collins Aerospace",
        "title": "Lead Engineer - DEMPA",
        "location": "Bangalore",
        "fit_score": 5,
        "skills_matched": ["Cameo", "SysML", "MATLAB"],
        "apply_url": "https://example.com/rtx",
        "next_action": "Draft tailored resume"
    }]
    text, html = generate_digest(roles, candidate_name="Mansi")
    assert "Collins Aerospace" in text
    assert "https://example.com/rtx" in text
    assert "<html>" in html
    assert "Collins Aerospace" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_notifier.py -v`  
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `scripts/notifier.py`**

Implement:
- `filter_unnotified_roles`: Filters out roles already in `reports/sent_history.json` and below `min_fit_score=3`.
- `generate_digest`: Generates crisp, clean executive plain-text and mobile-responsive HTML with direct apply buttons and skill matches.
- `dispatch_email`: Uses `gmail mutate send` CLI command (or supports `--dry-run` to print or save artifact without executing external send).
- Records sent role IDs to `reports/sent_history.json` and archives copy in `reports/YYYY-MM-DD-digest.html`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_notifier.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/notifier.py tests/test_notifier.py
git commit -m "feat: add weekly digest generator and email dispatcher"
```

---

### Task 5: Multi-Tier Search & Discovery Utilities (`scripts/search_engine.py`)

**Files:**
- Create: `scripts/search_engine.py`
- Test: `tests/test_search_engine.py`

**Interfaces:**
- Produces: `generate_tier1_dorking_queries(candidate: dict) -> list[str]`
- Produces: `query_public_ats_feed(company: dict) -> list[dict]`
- Produces: CLI `python scripts/search_engine.py [--queries | --scan-ats]`

- [ ] **Step 1: Write test for search utilities**

```python
# tests/test_search_engine.py
from scripts.search_engine import generate_tier1_dorking_queries

def test_generate_dorking_queries():
    candidate = {
        "core_skills": ["MBSE", "SysML"],
        "target_locations": ["Bangalore"]
    }
    queries = generate_tier1_dorking_queries(candidate)
    assert any("site:linkedin.com/jobs" in q for q in queries)
    assert any("Bangalore" in q for q in queries)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_search_engine.py -v`  
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `scripts/search_engine.py`**

Implement:
- Google Dorking query generators for public LinkedIn job pages and general aggregator boards.
- Lightweight HTTP client querying public ATS endpoints for target companies using standard Workday / Greenhouse JSON APIs.
- Output formatting for ingest into `data/openings.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_search_engine.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/search_engine.py tests/test_search_engine.py
git commit -m "feat: add search engine dorking and ATS discovery utilities"
```

---

### Task 6: Agent Operating Manual (`GEMINI.md`) & Runbook (`README.md`)

**Files:**
- Create: `GEMINI.md`
- Create: `README.md`
- Test: `tests/test_runbook.py` (verifies CLI end-to-end dry run)

**Interfaces:**
- Produces: Complete agent constitution and documentation for running, testing, and scheduling the pipeline.

- [ ] **Step 1: Write end-to-end integration test**

```python
# tests/test_runbook.py
import subprocess
import sys

def test_cli_dry_run_pipeline():
    result = subprocess.run([
        sys.executable, "scripts/notifier.py", "--dry-run"
    ], capture_output=True, text=True)
    assert result.returncode == 0
    assert "Digest Preview" in result.stdout or "No new roles" in result.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_runbook.py -v`  
Expected: FAIL (notifier CLI not integrated yet)

- [ ] **Step 3: Create `GEMINI.md` and `README.md`**

1. Write `GEMINI.md`:
   - Profile overview for Mansi.
   - Operating rules: Always sync JSON to Markdown, always enforce LinkedIn safety envelope (jitter, caps, duty cycle).
   - Agent workflows:
     - `/discover`: Agent executes Tier 1 web search queries, ingests hits, scores via `scripts/scorer.py`.
     - `/sync`: Runs `python scripts/sync_tracker.py`.
     - `/digest`: Runs `python scripts/notifier.py --dry-run` to preview email.
     - `/email`: Dispatches email to Mansi via `python scripts/notifier.py --send`.
2. Write `README.md`:
   - Clean quickstart, directory explanation, running tests, manual overrides.
3. Ensure CLI flags in `scripts/notifier.py` support `--dry-run` and `--send`.

- [ ] **Step 4: Run end-to-end test and pytest suite**

Run: `pytest tests/ -v`  
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add GEMINI.md README.md scripts/ tests/
git commit -m "docs: add GEMINI.md agent operating manual and README runbook"
```
