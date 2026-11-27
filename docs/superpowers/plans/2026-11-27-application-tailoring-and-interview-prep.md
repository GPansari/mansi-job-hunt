# Application Tailoring, Reviewer Audit & Interview Prep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-role JD analysis, tailored resume/cover-letter generation (HTML-to-PDF), fact-checking ATS review, interview prep packs, and cross-role upskill reporting to `Mansi Job Hunt`—porting the best workflows of `ai-job-search-dev/ai-job-search` onto the existing Python + Antigravity pipeline without disrupting discovery or weekly digests.

**Architecture:** Build a zero-external-dependency Python layer (`scripts/profile_loader.py`, `scripts/jd_analyzer.py`, `scripts/application_builder.py`, `scripts/application_reviewer.py`, `scripts/interview_prep.py`, `scripts/upskill_analyzer.py`) backed by a verified markdown dossier (`profile/master_dossier.md`), semantic print-CSS HTML templates (`templates/`), headless Chrome PDF compilation, and a workspace skill (`.agents/skills/job-application-coach/SKILL.md`). Each per-role package lives in `applications/<opening-id>/` so `data/openings.json`, `data/Openings_Tracker.md`, and `scripts/notifier.py` remain untouched as the canonical tracking and digest layers.

**Tech Stack:** Python 3.10+ (stdlib `html`, `json`, `re`, `string.Template`, `subprocess`, `urllib`/`requests`), macOS `pdftotext` (`/opt/homebrew/bin/pdftotext`), `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` (`--headless --print-to-pdf`), `pytest`.

**Spec:** Derived from user evaluation of `ai-job-search-dev/ai-job-search` against `GEMINI.md` and current `Mansi Job Hunt` architecture.

## Global Constraints

- Preserve Python 3.10+ standard-library-first runtime (only `requests` is already used in `scripts/search_engine.py`; do not add `weasyprint`, `jinja2`, `pypdf`, or `pdflatex` dependencies).
- Never auto-submit applications or auto-scrape LinkedIn URLs (`GEMINI.md` Section 2.6 & Section 3).
- Keep `data/openings.json` and `data/Openings_Tracker.md` schema unchanged so all 59 existing tests in `tests/` continue passing.
- Escape all dynamic strings rendered into HTML with `html.escape(..., quote=True)` (`GEMINI.md` Section 8.3).
- Every tailored resume, cover letter, and interview prep artifact may cite only facts present in `profile/master_dossier.md` and `profile/candidate.json`.
- Gitignore generated personal application outputs (`applications/`) while keeping `templates/`, `scripts/`, and `.agents/skills/` tracked.

## Review Focus

- **Unverified claim / hallucination in draft:** Draft contains a standard, tool, or metric (e.g., `DO-254` or `SysML v2`) absent from `profile/master_dossier.md` and `profile/candidate.json` -> `audit_application` flags it in `unverified_claims` and sets `passed = False`. (Covered in Task 4)
- **Automated LinkedIn scraping attempt:** `fetch_jd_text("https://www.linkedin.com/jobs/view/123")` -> raises `ValueError` instructing the operator to pass `--jd-file` or `--jd-text`. (Covered in Task 2)
- **HTML special characters in titles/rationales:** Titles with `&`, `<`, `>`, or quotes (e.g., `Senior Lead Dev & V&V <Avionics>`) -> `render_html_from_template` escapes all values cleanly without breaking markup. (Covered in Task 3)
- **Missing Chrome binary for PDF compilation:** Running `compile_html_to_pdf` when `chrome_bin` does not exist -> returns `False` cleanly while keeping `.html` and `.json` artifacts intact. (Covered in Task 3)
- **Unresolved placeholders or empty `applications/` state:** Draft containing `TBD` / `[Company]` fails review; `aggregate_skill_gaps` with zero `analysis.json` files returns a valid zero-count summary instead of crashing. (Covered in Tasks 4 & 5)

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `profile/master_dossier.md` | Create | Verified markdown career dossier extracted from `profile/Mansi_Agrawal_Resume.pdf` (facts, metrics, programs, standards, boundaries) |
| `scripts/profile_loader.py` | Create | Load `candidate.json` + `master_dossier.md`, extract PDF text via `pdftotext`, parse verified entities/facts |
| `scripts/jd_analyzer.py` | Create | Fetch non-LinkedIn JDs or read pasted JD files, compute matched skills/standards & skill gaps, save `applications/<id>/analysis.{json,md}` |
| `templates/resume.html` | Create | Print-ready ATS-friendly HTML5 resume template (`@page` A4/Letter CSS, `string.Template` placeholders) |
| `templates/cover_letter.html` | Create | Print-ready HTML5 cover letter template matching resume typography |
| `scripts/application_builder.py` | Create | Draft tailored resume & cover letter from verified dossier + JD analysis, render HTML, compile PDF via headless Chrome |
| `scripts/application_reviewer.py` | Create | Fact-check tailored drafts against `master_dossier.md`, compute ATS keyword coverage, check placeholders/contact/page count |
| `scripts/interview_prep.py` | Create | Generate `applications/<id>/interview_prep.md` with technical topics, grounded STAR prompts, and panel questions |
| `scripts/upskill_analyzer.py` | Create | Aggregate recurring `skill_gaps` across analyzed roles into `reports/upskill_summary.md` |
| `.agents/skills/job-application-coach/SKILL.md` | Create | Antigravity skill defining `/apply`, `/review-app`, `/interview`, and `/upskill` multi-agent procedures |
| `.gitignore` | Modify | Add `applications/` so generated per-role PDFs/drafts stay local and private |
| `GEMINI.md` & `README.md` | Modify | Document Phase 2 commands and application workflow |
| `tests/test_profile_loader.py` | Create | Unit tests for dossier parsing, verified facts extraction, and `pdftotext` wrapper |
| `tests/test_jd_analyzer.py` | Create | Unit tests for LinkedIn URL guard, HTML stripping, gap detection, and artifact saving |
| `tests/test_application_builder.py` | Create | Unit tests for tailoring, HTML escaping, template rendering, and Chrome fallback |
| `tests/test_application_reviewer.py` | Create | Unit tests for hallucination detection, ATS coverage, placeholders, and contact checks |
| `tests/test_interview_and_upskill.py` | Create | Unit tests for interview prep generation and empty/populated upskill aggregation |

---

### Task 1: Master Candidate Dossier & Profile Loader

**Files:**
- Create: `profile/master_dossier.md`
- Create: `scripts/profile_loader.py`
- Test: `tests/test_profile_loader.py`

**Interfaces:**
- Consumes: `profile/candidate.json`, `profile/Mansi_Agrawal_Resume.pdf` (via `pdftotext` during initial authoring)
- Produces:
  - `extract_pdf_text(pdf_path: Path) -> str`
  - `extract_verified_facts(dossier_markdown: str, candidate: dict[str, Any]) -> dict[str, list[str]]`
  - `load_master_profile(candidate_path: Path = Path("profile/candidate.json"), dossier_path: Path = Path("profile/master_dossier.md")) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test in `tests/test_profile_loader.py`**

```python
from pathlib import Path
import pytest
from scripts.profile_loader import (
    extract_pdf_text,
    extract_verified_facts,
    load_master_profile,
)

def test_extract_verified_facts_parses_sections_and_candidate():
    dossier = (
        "# Master Dossier\n\n"
        "## Verified Companies\n- Boeing India\n- Collins Aerospace\n\n"
        "## Verified Programs\n- Boeing 777-8F Digital Transformation (DTx)\n\n"
        "## Verified Standards\n- ARP4754A\n- DO-178C\n\n"
        "## Verified Metrics\n- Leads a team of 5 engineers and mentors 4 more\n"
    )
    candidate = {
        "name": "Mansi Agrawal",
        "core_skills": ["MBSE", "SysML", "Cameo"],
        "education": "MS Aerospace Engineering, Georgia Tech",
    }
    facts = extract_verified_facts(dossier, candidate)
    assert "Boeing India" in facts["companies"]
    assert "ARP4754A" in facts["standards"]
    assert "MBSE" in facts["skills_and_tools"]
    assert "MS Aerospace Engineering, Georgia Tech" in facts["education"]

def test_load_master_profile_missing_dossier_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_master_profile(
            candidate_path=Path("profile/candidate.json"),
            dossier_path=tmp_path / "missing.md",
        )

def test_extract_pdf_text_reads_resume():
    text = extract_pdf_text(Path("profile/Mansi_Agrawal_Resume.pdf"))
    assert "Mansi" in text
    assert len(text.strip()) > 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_profile_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.profile_loader'`

- [ ] **Step 3: Extract `profile/Mansi_Agrawal_Resume.pdf` text and author `profile/master_dossier.md`**

Run: `pdftotext profile/Mansi_Agrawal_Resume.pdf -`
Author `profile/master_dossier.md` using **only** facts directly present in the extracted resume text and `profile/candidate.json`, organized under exact `## ` headings:
- `## Summary`
- `## Verified Companies`
- `## Verified Programs`
- `## Experience` (role, company, period, bulleted verified achievements)
- `## Verified Standards`
- `## Verified Skills & Tools`
- `## Verified Metrics`
- `## Education`
- `## Target Scope & Deal-Breakers`

- [ ] **Step 4: Implement `scripts/profile_loader.py`**

Implement:
- `extract_pdf_text(pdf_path: Path) -> str` using `subprocess.run(["pdftotext", str(pdf_path), "-"], capture_output=True, text=True, check=True)`
- `parse_dossier_sections(dossier_markdown: str) -> dict[str, str]` splitting on `## <Heading>`
- `extract_verified_facts(dossier_markdown: str, candidate: dict[str, Any]) -> dict[str, list[str]]` collecting bullet items (`- ...`) per verified section and merging `candidate["core_skills"]` and `candidate["education"]` with case-preserved deduplication
- `load_master_profile(candidate_path: Path = Path("profile/candidate.json"), dossier_path: Path = Path("profile/master_dossier.md")) -> dict[str, Any]` raising `FileNotFoundError` if either file is missing

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_profile_loader.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add profile/master_dossier.md scripts/profile_loader.py tests/test_profile_loader.py
git commit -m "feat: add verified master dossier and profile loader"
```

---

### Task 2: Deep JD Fetcher & Qualitative Alignment Analyzer

**Files:**
- Create: `scripts/jd_analyzer.py`
- Test: `tests/test_jd_analyzer.py`

**Interfaces:**
- Consumes: `load_master_profile` from `scripts/profile_loader.py`, `SKILL_ALIASES` / `load_candidate_profile` from `scripts/scorer.py`, `data/openings.json`
- Produces:
  - `load_opening_by_id(opening_id: str, openings_path: Path = Path("data/openings.json")) -> dict[str, Any]`
  - `fetch_jd_text(url: str, timeout: int = 15) -> str`
  - `analyze_jd(opening: dict[str, Any], jd_text: str, master_profile: dict[str, Any]) -> dict[str, Any]`
  - `save_analysis(analysis: dict[str, Any], applications_dir: Path = Path("applications")) -> tuple[Path, Path]`

- [ ] **Step 1: Write the failing test in `tests/test_jd_analyzer.py`**

```python
import pytest
from pathlib import Path
from scripts.jd_analyzer import (
    analyze_jd,
    fetch_jd_text,
    load_opening_by_id,
    save_analysis,
)
from scripts.profile_loader import load_master_profile

def test_fetch_jd_text_blocks_linkedin_urls():
    with pytest.raises(ValueError, match="LinkedIn"):
        fetch_jd_text("https://www.linkedin.com/jobs/view/1234567890")

def test_load_opening_by_id_finds_known_opening():
    op = load_opening_by_id("AIRBUS-JR10437140")
    assert op["company"] == "Airbus India"

def test_analyze_jd_identifies_matched_skills_and_gaps():
    profile = load_master_profile()
    opening = {
        "id": "TEST-1",
        "company": "Airbus India",
        "title": "Lead Systems Engineer - MBSE",
        "location": "Bangalore",
        "seniority": "Lead",
        "skills_matched": ["MBSE", "SysML"],
    }
    jd_text = (
        "Seeking Lead Systems Engineer in Bangalore with Cameo Systems Modeler, "
        "SysML, ARP4754A, DO-178C, and Teamcenter Polarion experience."
    )
    result = analyze_jd(opening, jd_text, profile)
    assert "Cameo" in result["matched_skills"] or "SysML" in result["matched_skills"]
    assert "ARP4754A" in result["matched_standards"]
    assert isinstance(result["skill_gaps"], list)
    assert any("polarion" in g.lower() or "teamcenter" in g.lower() for g in result["skill_gaps"])

def test_save_analysis_writes_json_and_markdown(tmp_path):
    analysis = {
        "opening_id": "TEST-1",
        "company": "Airbus India",
        "title": "Lead Systems Engineer",
        "matched_skills": ["MBSE", "SysML"],
        "skill_gaps": ["Polarion"],
        "matched_standards": ["ARP4754A"],
        "missing_standards": [],
        "seniority_alignment": "Strong",
        "location_alignment": "Bangalore match",
        "priority_keywords": ["MBSE", "SysML", "ARP4754A"],
        "recommended_angles": ["Highlight 777-8F DTx MBSE leadership"],
        "analyzed_at": "2026-11-27",
    }
    json_path, md_path = save_analysis(analysis, applications_dir=tmp_path)
    assert json_path == tmp_path / "TEST-1" / "analysis.json"
    assert md_path == tmp_path / "TEST-1" / "analysis.md"
    assert json_path.exists() and md_path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_jd_analyzer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.jd_analyzer'`

- [ ] **Step 3: Implement `scripts/jd_analyzer.py`**

Implement:
- `fetch_jd_text(url: str, timeout: int = 15) -> str`: Reject `linkedin.com` hostnames with `ValueError("LinkedIn URLs must not be auto-scraped; pass --jd-file or --jd-text instead.")`; for Workday/Greenhouse/Lever/Freshteam/Ashby HTML, fetch via `requests.get` with a standard browser `User-Agent`, strip `<script>`/`<style>`/tags, and normalize whitespace.
- `load_opening_by_id(...)` reading `data/openings.json` and raising `KeyError` if not found.
- `analyze_jd(...)`: Match candidate skills (reusing `SKILL_ALIASES` from `scripts/scorer.py`) and known aerospace standards (`ARP4754A`, `ARP4761`, `DO-178C`, `DO-254`, `DO-160`, `AS9100`, `ISO 26262`, `SysML v2`, `MOSA`, `ARINC 429`, `AFDX`, `MIL-STD-882E`) against `jd_text` and `verified_facts`; detect gap terms from a curated aerospace/MBSE tool/standard dictionary (`Polarion`, `Teamcenter`, `Rhapsody`, `Capella`, `Enterprise Architect`, `SysML v2`, `Simulink`, `LabVIEW`, `Jama`, `Windchill`, `SCADE`) that appear in `jd_text` but are absent from `verified_facts["skills_and_tools"]` + `verified_facts["standards"]`.
- `save_analysis(...)`: Write `analysis.json` and formatted `analysis.md` under `applications/<opening_id>/`.
- CLI entrypoint (`python scripts/jd_analyzer.py --id <OPENING_ID> [--jd-file PATH | --jd-text TEXT | --fetch]`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_jd_analyzer.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/jd_analyzer.py tests/test_jd_analyzer.py
git commit -m "feat: add JD analyzer with LinkedIn guard and gap detection"
```

---

### Task 3: Tailored Resume & Cover Letter Templates + PDF Compiler

**Files:**
- Create: `templates/resume.html`
- Create: `templates/cover_letter.html`
- Create: `scripts/application_builder.py`
- Test: `tests/test_application_builder.py`

**Interfaces:**
- Consumes: `load_master_profile` (`scripts/profile_loader.py`), `load_opening_by_id`, `analyze_jd`, `save_analysis` (`scripts/jd_analyzer.py`)
- Produces:
  - `build_tailored_resume_data(opening: dict[str, Any], analysis: dict[str, Any], master_profile: dict[str, Any]) -> dict[str, Any]`
  - `draft_cover_letter_markdown(opening: dict[str, Any], analysis: dict[str, Any], master_profile: dict[str, Any]) -> str`
  - `render_html_from_template(template_path: Path, context: dict[str, str]) -> str`
  - `compile_html_to_pdf(html_path: Path, pdf_path: Path, chrome_bin: Path = DEFAULT_CHROME_BIN) -> bool`
  - `build_application_package(opening_id: str, jd_text: str | None = None, applications_dir: Path = Path("applications"), render_pdf: bool = True) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test in `tests/test_application_builder.py`**

```python
from pathlib import Path
from scripts.application_builder import (
    build_tailored_resume_data,
    compile_html_to_pdf,
    draft_cover_letter_markdown,
    render_html_from_template,
)
from scripts.profile_loader import load_master_profile

def test_render_html_from_template_escapes_special_characters(tmp_path):
    tpl = tmp_path / "sample.html"
    tpl.write_text("<h1>$TITLE</h1><p>$COMPANY</p>", encoding="utf-8")
    rendered = render_html_from_template(
        tpl,
        {"TITLE": 'Lead Dev & V&V <"Avionics">', "COMPANY": "Collins & RTX"},
    )
    assert "&amp;" in rendered
    assert "&lt;" in rendered
    assert "Collins &amp; RTX" in rendered

def test_compile_html_to_pdf_handles_missing_chrome_gracefully(tmp_path):
    html_file = tmp_path / "doc.html"
    html_file.write_text("<html><body><h1>Hello</h1></body></html>", encoding="utf-8")
    pdf_file = tmp_path / "doc.pdf"
    ok = compile_html_to_pdf(html_file, pdf_file, chrome_bin=tmp_path / "no-chrome")
    assert ok is False
    assert not pdf_file.exists()

def test_tailored_resume_and_cover_letter_grounding():
    profile = load_master_profile()
    opening = {
        "id": "RTX-01889489",
        "company": "Collins Aerospace (RTX)",
        "title": "Principal Engineer - Systems Requirements Architect",
        "location": "Bangalore",
        "skills_matched": ["MBSE", "SysML", "Cameo", "DOORS"],
    }
    analysis = {
        "opening_id": "RTX-01889489",
        "matched_skills": ["MBSE", "SysML", "Cameo", "IBM DOORS"],
        "matched_standards": ["ARP4754A"],
        "skill_gaps": [],
        "priority_keywords": ["MBSE", "SysML", "Cameo", "DOORS", "ARP4754A"],
    }
    resume_data = build_tailored_resume_data(opening, analysis, profile)
    assert resume_data["name"] == "Mansi Agrawal"
    assert resume_data["core_skills"][0] in {"MBSE", "SysML", "Cameo", "IBM DOORS"}
    letter = draft_cover_letter_markdown(opening, analysis, profile)
    assert "Collins Aerospace (RTX)" in letter
    assert "TBD" not in letter
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_application_builder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.application_builder'`

- [ ] **Step 3: Create `templates/resume.html` and `templates/cover_letter.html`**

- Clean single-column ATS-parseable HTML5 + CSS `@page { size: A4; margin: 14mm 16mm; }` layout using system sans-serif typography, clean borders, `string.Template` tokens (`$NAME`, `$HEADLINE`, `$CONTACT_LINE`, `$SUMMARY`, `$SKILLS_HTML`, `$EXPERIENCE_HTML`, `$EDUCATION_HTML` for `resume.html`; `$NAME`, `$CONTACT_LINE`, `$DATE`, `$COMPANY`, `$ROLE`, `$BODY_HTML` for `cover_letter.html`).

- [ ] **Step 4: Implement `scripts/application_builder.py`**

- Prioritize `core_skills` matching `analysis["priority_keywords"]` first, followed by remaining verified skills from `candidate.json`.
- Parse `Experience` roles and bullets from `master_dossier.md` and score/order bullets per role by keyword overlap with `priority_keywords` without altering factual wording.
- Escape every interpolated string with `html.escape(val, quote=True)` inside `render_html_from_template` (using `SAFE_HTML` suffix or explicit pre-escaped HTML fragments for `$SKILLS_HTML`/`$EXPERIENCE_HTML`/`$EDUCATION_HTML`/`$BODY_HTML`, escaping every leaf text node before joining).
- `compile_html_to_pdf` checks `chrome_bin.exists()`, invokes `[str(chrome_bin), "--headless=new", "--disable-gpu", "--no-sandbox", f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer", html_path.resolve().as_uri()]`, and returns `pdf_path.exists()`.
- CLI entrypoint (`python scripts/application_builder.py --id <OPENING_ID> [--jd-file PATH] [--no-pdf]`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_application_builder.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add templates/resume.html templates/cover_letter.html scripts/application_builder.py tests/test_application_builder.py
git commit -m "feat: add tailored resume/cover-letter builder and HTML-to-PDF renderer"
```

---

### Task 4: Fact-Checking Reviewer & ATS Audit Gate

**Files:**
- Create: `scripts/application_reviewer.py`
- Test: `tests/test_application_reviewer.py`

**Interfaces:**
- Consumes: `load_master_profile` (`scripts/profile_loader.py`), `applications/<id>/{tailored_resume.json, cover_letter.md, analysis.json, tailored_resume.pdf}`
- Produces:
  - `audit_application(opening_id: str, applications_dir: Path = Path("applications"), master_profile: dict[str, Any] | None = None, candidate_path: Path = Path("profile/candidate.json"), dossier_path: Path = Path("profile/master_dossier.md")) -> dict[str, Any]`
  - `save_review_report(report: dict[str, Any], applications_dir: Path = Path("applications")) -> tuple[Path, Path]`

- [ ] **Step 1: Write the failing test in `tests/test_application_reviewer.py`**

```python
import json
from scripts.application_reviewer import audit_application, save_review_report

def _seed_app_dir(tmp_path, opening_id="TEST-REV", resume_skills=None, letter_text="Dear Hiring Team,\nApplying with MBSE and SysML experience.\nRegards,\nMansi Agrawal"):
    app_dir = tmp_path / opening_id
    app_dir.mkdir(parents=True)
    (app_dir / "analysis.json").write_text(json.dumps({
        "opening_id": opening_id,
        "priority_keywords": ["MBSE", "SysML", "Cameo"],
        "matched_skills": ["MBSE", "SysML"],
        "skill_gaps": [],
    }), encoding="utf-8")
    (app_dir / "tailored_resume.json").write_text(json.dumps({
        "opening_id": opening_id,
        "name": "Mansi Agrawal",
        "email": "agrawal.mansi20@gmail.com",
        "phone": "+91-8779232450",
        "headline": "Lead Systems Engineer",
        "summary": "10 years in MBSE and SysML.",
        "core_skills": resume_skills or ["MBSE", "SysML", "Cameo"],
        "experience": [{"role": "Lead Systems Engineer", "company": "Boeing India", "bullets": ["Led MBSE adoption"]}],
        "education": ["MS Aerospace Engineering, Georgia Tech"],
    }), encoding="utf-8")
    (app_dir / "cover_letter.md").write_text(letter_text, encoding="utf-8")
    return app_dir

def test_audit_flags_unverified_standard_claim(tmp_path):
    _seed_app_dir(
        tmp_path,
        resume_skills=["MBSE", "SysML", "DO-254", "SysML v2"],
        letter_text="I led SysML v2 certification at Airbus.",
    )
    report = audit_application("TEST-REV", applications_dir=tmp_path)
    assert report["passed"] is False
    assert len(report["unverified_claims"]) >= 1

def test_audit_flags_unresolved_placeholders(tmp_path):
    _seed_app_dir(
        tmp_path,
        letter_text="Dear [Hiring Manager], TBD for [Company].",
    )
    report = audit_application("TEST-REV", applications_dir=tmp_path)
    assert report["passed"] is False
    assert any("TBD" in hit or "[" in hit for hit in report["placeholder_hits"])

def test_audit_passes_clean_grounded_application(tmp_path):
    _seed_app_dir(tmp_path)
    report = audit_application("TEST-REV", applications_dir=tmp_path)
    assert report["passed"] is True
    assert report["ats_coverage_pct"] == 100.0
    json_p, md_p = save_review_report(report, applications_dir=tmp_path)
    assert json_p.exists() and md_p.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_application_reviewer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.application_reviewer'`

- [ ] **Step 3: Implement `scripts/application_reviewer.py`**

Implement checks inside `audit_application(...)`:
1. **Contact fidelity:** Verify `name`, `email`, `phone` in `tailored_resume.json` match `candidate.json`.
2. **Unverified claims:** Check all aerospace standards (`ARP4754A`, `ARP4761`, `DO-178C`, `DO-254`, `DO-160`, `AS9100`, `SysML v2`, `MOSA`, `ARINC 429`, `AFDX`, `MIL-STD-882E`) and listed `core_skills` / `experience[].company` appearing in `tailored_resume.json` or `cover_letter.md` against `master_profile["verified_facts"]`; any item not present in the verified dossier/candidate profile is added to `unverified_claims`.
3. **Placeholder check:** Detect `TBD`, `TODO`, `FIXME`, `[Company]`, `[Hiring Manager]`, `{{...}}` in `placeholder_hits`.
4. **ATS coverage:** Percentage of `analysis["priority_keywords"]` present (case-insensitive) in combined resume + cover letter text.
5. **PDF page budget (when `tailored_resume.pdf` exists):** Use `pdfinfo` or `pdftotext` form-feed count (`\x0c`) to check `page_count <= 2`.
6. Set `passed = (len(unverified_claims) == 0 and len(placeholder_hits) == 0 and len(contact_mismatch) == 0 and (page_count is None or page_count <= 2))`.
7. CLI entrypoint (`python scripts/application_reviewer.py --id <OPENING_ID>`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_application_reviewer.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/application_reviewer.py tests/test_application_reviewer.py
git commit -m "feat: add fact-checking and ATS application reviewer"
```

---

### Task 5: Interview Prep Generator & Cross-Role Upskill Analyzer

**Files:**
- Create: `scripts/interview_prep.py`
- Create: `scripts/upskill_analyzer.py`
- Test: `tests/test_interview_and_upskill.py`

**Interfaces:**
- Consumes: `load_master_profile` (`scripts/profile_loader.py`), `load_opening_by_id` (`scripts/jd_analyzer.py`), `applications/*/analysis.json`, `data/openings.json`
- Produces:
  - `generate_interview_prep(opening_id: str, applications_dir: Path = Path("applications"), openings_path: Path = Path("data/openings.json")) -> Path`
  - `aggregate_skill_gaps(applications_dir: Path = Path("applications"), openings_path: Path = Path("data/openings.json")) -> dict[str, Any]`
  - `write_upskill_report(summary: dict[str, Any], output_path: Path = Path("reports/upskill_summary.md")) -> Path`

- [ ] **Step 1: Write the failing test in `tests/test_interview_and_upskill.py`**

```python
import json
from scripts.interview_prep import generate_interview_prep
from scripts.upskill_analyzer import aggregate_skill_gaps, write_upskill_report

def test_generate_interview_prep_creates_grounded_pack(tmp_path):
    app_dir = tmp_path / "AIRBUS-JR10437140"
    app_dir.mkdir(parents=True)
    (app_dir / "analysis.json").write_text(json.dumps({
        "opening_id": "AIRBUS-JR10437140",
        "company": "Airbus India",
        "title": "Modelling and Simulation Systems Engineering",
        "matched_skills": ["MBSE", "SysML"],
        "skill_gaps": ["Polarion"],
        "matched_standards": ["ARP4754A"],
        "priority_keywords": ["MBSE", "SysML"],
    }), encoding="utf-8")
    out_path = generate_interview_prep("AIRBUS-JR10437140", applications_dir=tmp_path)
    content = out_path.read_text(encoding="utf-8")
    assert out_path == app_dir / "interview_prep.md"
    assert "Airbus India" in content
    assert "Boeing" in content
    assert "Polarion" in content

def test_aggregate_skill_gaps_handles_empty_applications_dir(tmp_path):
    summary = aggregate_skill_gaps(applications_dir=tmp_path)
    assert summary["analyzed_count"] == 0
    assert summary["top_gaps"] == []
    report_path = write_upskill_report(summary, output_path=tmp_path / "upskill.md")
    assert report_path.exists()

def test_aggregate_skill_gaps_ranks_recurring_gaps(tmp_path):
    for idx, gaps in enumerate([["SysML v2", "Polarion"], ["SysML v2", "Capella"]]):
        d = tmp_path / f"OP-{idx}"
        d.mkdir()
        (d / "analysis.json").write_text(json.dumps({
            "opening_id": f"OP-{idx}",
            "company": "TestCo",
            "title": "Lead SE",
            "skill_gaps": gaps,
        }), encoding="utf-8")
    summary = aggregate_skill_gaps(applications_dir=tmp_path)
    assert summary["analyzed_count"] == 2
    assert summary["top_gaps"][0]["skill"] == "SysML v2"
    assert summary["top_gaps"][0]["count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_interview_and_upskill.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `scripts/interview_prep.py` and `scripts/upskill_analyzer.py`**

- `scripts/interview_prep.py`: Combines opening metadata, `analysis.json` (if present; otherwise synthesizes from opening's `skills_matched` & `fit_rationale`), and `master_profile` to write `applications/<opening_id>/interview_prep.md` with sections: `Role Snapshot`, `Technical Deep-Dive Topics`, `Grounded STAR Story Bank` (pulling verified experience bullets from `master_dossier.md`), `Gap Mitigation Talking Points`, and `Questions for the Interview Panel`.
- `scripts/upskill_analyzer.py`: Scans `applications/*/analysis.json`, tallies gap frequencies using `collections.Counter`, ranks `top_gaps` (`[{"skill", "count", "openings"}]`), and writes `reports/upskill_summary.md`.
- CLI entrypoints for both scripts (`--id <OPENING_ID>` and `--output reports/upskill_summary.md`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_interview_and_upskill.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/interview_prep.py scripts/upskill_analyzer.py tests/test_interview_and_upskill.py
git commit -m "feat: add interview prep generator and cross-role upskill analyzer"
```

---

### Task 6: Antigravity Workspace Skill, `.gitignore`, and Documentation

**Files:**
- Create: `.agents/skills/job-application-coach/SKILL.md`
- Modify: `.gitignore`
- Modify: `GEMINI.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: CLI scripts from Tasks 1–5
- Produces: Discoverable Antigravity workspace skill documenting `/apply <id>`, `/review-app <id>`, `/interview <id>`, and `/upskill` workflows, plus Drafter -> Reviewer subagent instructions.

- [ ] **Step 1: Add `applications/` to `.gitignore`**

Append `applications/` to `.gitignore` so tailored per-role resumes/cover letters/PDFs stay local and private.

- [ ] **Step 2: Author `.agents/skills/job-application-coach/SKILL.md`**

Include YAML frontmatter (`name: job-application-coach`, `description: ...`) and step-by-step instructions for:
1. Analyzing a shortlisted opening (`scripts/jd_analyzer.py`)
2. Building tailored resume + cover letter (`scripts/application_builder.py`)
3. Running `scripts/application_reviewer.py` **plus** spawning a fresh `research`/`self` reviewer subagent to qualitatively critique tone and alignment before human submission
4. Generating interview prep (`scripts/interview_prep.py`) and upskill reports (`scripts/upskill_analyzer.py`)
5. Updating `data/openings.json` status/next_action and running `python scripts/sync_tracker.py --to-md` after Mansi applies manually.

- [ ] **Step 3: Document Phase 2 workflows in `GEMINI.md` and `README.md`**

Add concise CLI usage examples and directory map entries for `profile/master_dossier.md`, `templates/`, `applications/`, and the new scripts without altering existing Sections 1–3 rules.

- [ ] **Step 4: Run full verification suite & dry-run smoke check**

Run: `pytest -v`
Expected: All existing 59 tests + all new tests pass with 0 failures and 0 skipped tests.

Run: `python scripts/upskill_analyzer.py --output reports/upskill_summary.md`
Expected: Exits 0 and writes `reports/upskill_summary.md`.

- [ ] **Step 5: Commit**

```bash
git add .gitignore .agents/skills/job-application-coach/SKILL.md GEMINI.md README.md
git commit -m "docs: add job-application-coach skill and Phase 2 workflow docs"
```
