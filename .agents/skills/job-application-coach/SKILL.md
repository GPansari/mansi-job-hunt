---
name: job-application-coach
description: >-
  End-to-end Phase 2 job application coaching workflow for Mansi Agrawal:
  deep JD alignment analysis, dossier-grounded resume and cover letter tailoring,
  automated + subagent fact-checking review, interview preparation packs, and
  cross-role upskill gap aggregation. Use for /apply <id>, /review-app <id>,
  /interview <id>, and /upskill.
---

# Job Application Coach

Phase 2 coaching workflow for turning shortlisted openings in `data/openings.json` into verified, tailored application packages, interview prep packs, and upskill plans for **Mansi Agrawal**.

---

## Core Guardrails (Non-Negotiable)

1. **Strict Dossier Grounding**: Every role, employer, date, metric, tool, and aerospace standard in any tailored resume, cover letter, or interview prep document MUST come from [`profile/master_dossier.md`](file:///Users/gp/Desktop/GP%20Github%20Local/Mansi%20Job%20Hunt/profile/master_dossier.md) and [`profile/candidate.json`](file:///Users/gp/Desktop/GP%20Github%20Local/Mansi%20Job%20Hunt/profile/candidate.json). Never fabricate or extrapolate unverified claims.
2. **Human-in-the-Loop Submission**: Never submit applications or message recruiters on Mansi's behalf. Only Mansi submits manually after reviewing the audited PDFs.
3. **No Automated LinkedIn Scraping**: Never run `--fetch` against LinkedIn URLs (`jd_analyzer.py` blocks LinkedIn hosts). For LinkedIn roles, ask the operator to copy-paste the JD text or save it to a local file, then pass `--jd-file` or `--jd-text`.
4. **Workspace Privacy**: Per-role artifacts live under `applications/<opening_id>/` (gitignored via `.gitignore`). Never commit private tailored resumes or cover letters.
5. **Preserve Constitution Rules**: Follow all rules in `GEMINI.md` Sections 1–3 (`fit_score >= 3.0`, dual-tracker sync, requisition-specific links, LinkedIn safety envelope).

---

## Workflows

### 1. `/apply <id>` — Analyze JD & Build Tailored Application Package

Given an opening `<id>` from `data/openings.json` (e.g., `AIRBUS-JR10437140`):

#### Step 1: Analyze JD Alignment (`scripts/jd_analyzer.py`)
Run JD analysis to extract matched skills, matched standards, skill gaps, missing standards, priority keywords, and recommended narrative angles:

```bash
# For non-LinkedIn public ATS URLs:
python scripts/jd_analyzer.py --id <id> --fetch

# For a locally saved JD file (or manually pasted LinkedIn JD):
python scripts/jd_analyzer.py --id <id> --jd-file path/to/jd.txt

# Or pass raw JD text directly:
python scripts/jd_analyzer.py --id <id> --jd-text "<pasted job description>"
```

Inspect the generated files:
- `applications/<id>/analysis.json`
- `applications/<id>/analysis.md`

#### Step 2: Build Tailored Resume, Cover Letter & PDFs (`scripts/application_builder.py`)
Generate the tailored package grounded in `profile/master_dossier.md` and `templates/{resume.html,cover_letter.html}`:

```bash
# Full build including headless Google Chrome PDF compilation:
python scripts/application_builder.py --id <id>

# Or skip PDF compilation when Chrome is unavailable / during iteration:
python scripts/application_builder.py --id <id> --no-pdf
```

Outputs created under `applications/<id>/`:
- `tailored_resume.json`
- `tailored_resume.html`
- `tailored_resume.pdf` (unless `--no-pdf`)
- `cover_letter.md`
- `cover_letter.html`
- `cover_letter.pdf` (unless `--no-pdf`)

#### Step 3: Mandatory Audit & Reviewer Gate
Immediately run `/review-app <id>` before handing the package to Mansi for submission.

---

### 2. `/review-app <id>` — Deterministic Audit + Drafter -> Reviewer Subagent Gate

Every application package must pass **both** the deterministic Python audit gate and a fresh qualitative subagent review before presentation.

#### Step 1: Deterministic Fact-Checking & ATS Audit (`scripts/application_reviewer.py`)
```bash
python scripts/application_reviewer.py --id <id>
```

What this checks:
- Contact fidelity against `profile/candidate.json`
- Zero unverified standards, tools, skills, or employer claims relative to `profile/master_dossier.md`
- Zero unresolved placeholders (`TBD`, `TODO`, `{{...}}`, etc.)
- ATS keyword coverage against `applications/<id>/analysis.json`
- `tailored_resume.pdf` page budget (`<= 2` pages)

Outputs:
- `applications/<id>/review.json`
- `applications/<id>/review.md`

If the script exits non-zero (`FAILED`), resolve every flagged mismatch, unverified claim, placeholder, or page-overflow issue, rebuild with `scripts/application_builder.py --id <id>`, and re-run `scripts/application_reviewer.py --id <id>` until it exits `0` (`PASSED`).

#### Step 2: Drafter -> Reviewer Qualitative Subagent Gate
Once `scripts/application_reviewer.py` passes, invoke a **fresh** `research` (read-only) or `self` subagent via `invoke_subagent` (never reuse drafting context) to perform an independent qualitative critique before human submission.

In the subagent prompt, provide:
- Paths to `applications/<id>/analysis.md`, `applications/<id>/tailored_resume.json`, `applications/<id>/tailored_resume.html`, `applications/<id>/cover_letter.md`, `applications/<id>/review.md`, and `profile/master_dossier.md`.
- Clear review rubric:
  1. **Tone & Seniority Calibration**: Does the summary and cover letter read like a 10+ year Lead/Staff Systems Engineer & MBSE leader (precise, technical, outcome-focused, zero generic AI phrasing)?
  2. **Alignment & Relevance**: Are the highest-signal aerospace/MBSE bullets prioritized for this specific role's domain and problems?
  3. **Grounding Double-Check**: Are there any subtle implied claims or buzzwords in `cover_letter.md` or `tailored_resume.json` that overreach `profile/master_dossier.md`?
  4. **Conciseness & Format**: Are bullets crisp and ATS-friendly, and are `tailored_resume.pdf` / `cover_letter.pdf` ready for human inspection?

Address any substantive issues raised by the reviewer subagent, re-run `application_builder.py` and `application_reviewer.py` if files changed, and only then present the audited PDFs and summary to the user.

---

### 3. `/interview <id>` — Generate Role-Specific Interview Prep Pack

Generate a grounded interview preparation guide for an opening `<id>`:

```bash
python scripts/interview_prep.py --id <id>
```

- Uses `applications/<id>/analysis.json` when present (or synthesizes alignment from `data/openings.json`).
- Outputs `applications/<id>/interview_prep.md` containing:
  - Role & company alignment snapshot
  - Verified STAR stories and metrics mapped from `profile/master_dossier.md`
  - Technical & MBSE/architecture deep-dive talking points
  - Gap-bridging narratives for `skill_gaps` / `missing_standards`
  - High-signal questions for Mansi to ask the hiring panel

---

### 4. `/upskill` — Cross-Role Skill Gap & Upskill Report

Aggregate recurring gaps across all analyzed openings under `applications/*/analysis.json`:

```bash
python scripts/upskill_analyzer.py --output reports/upskill_summary.md
```

- Tallies `skill_gaps` and `missing_standards` across all evaluated roles.
- Maps each recurring gap to Mansi's verified transferable baseline (e.g., Polarion/Jama -> IBM DOORS, 3DEXPERIENCE, DESE).
- Writes prioritized recommendations to `reports/upskill_summary.md`.

---

### 5. Post-Submission Tracker Sync (After Mansi Applies Manually)

Only after Mansi confirms she has submitted an application:
1. Update the opening's `status` (e.g., `"Applied"`), `last_updated`, and `next_action` in `data/openings.json` (or `data/Openings_Tracker.md`).
2. Synchronize both trackers immediately:
   ```bash
   # If data/openings.json was updated:
   python scripts/sync_tracker.py --to-md

   # If data/Openings_Tracker.md was edited manually:
   python scripts/sync_tracker.py --to-json
   ```
3. Optionally run `/interview <id>` right away so Mansi is prepared for recruiter screening.
