# Mansi Job Hunt — Pending Upgrade Steps & Agent Handoff

## 1. Current Baseline (Completed)
- **Repository:** `/Users/gp/Desktop/GP Github Local/Mansi Job Hunt`
- **Python / Pytest:** `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3` and `/Library/Frameworks/Python.framework/Versions/3.12/bin/pytest`
- **Test Status:** 106 passed, 0 failed (`pytest -v`)
- **Completed Across Phases 1–4:**
  - **Phase 1:** Pure-Python `pypdf` fallback in `scripts/profile_loader.py` and `scripts/application_reviewer.py`; inactive/dead/expired exclusion in `scripts/notifier.py` + unit tests; archived root stale duplicates (`Openings Tracker.md`, `Target Companies.md`) to `archive/legacy_docs/`; updated `README.md`; cleaned `data/openings.json` (removed 4 legacy `fit_score < 3` rows, backfilled `company_category` and `url_type`).
  - **Phase 2:** Updated Workday metadata for Airbus India, Collins Aerospace (RTX), and Pratt & Whitney (RTX) in `data/target_companies.json`; upgraded `scripts/search_engine.py` (`requests.Session()` retry/backoff, multi-query Workday search with pagination, Bangalore filtering, full JD fetch, Kula & Freshteam adapters, 3-tier `url_type` ingestion gate); upgraded `scripts/scorer.py` (`target_domains` + verified `master_dossier.md` skills); upgraded `scripts/verify_links.py` (3-tier `url_type` verification, soft-404 checks, Workday HTTP 429 kept as `rate_limited`, startup board role + CTA verification, per-domain rate limiting).
  - **Phase 3:** Created `scripts/linkedin_ingest.py` (`--from-json`, local `--cdp-url`, `LINKEDIN_SAFETY_ENVELOPE`, 40/day counter at `reports/linkedin_views.json`, immediate halt on CAPTCHA/HTTP 999, `LI-<company>-<job_id>` normalization, deduplication, `applications/<id>/jd_raw.txt` saving) and `scripts/linkedin_bookmarklet.js`; overhauled `scripts/generate_site.py` and `tests/test_generate_site.py` (Discovered column, 4 sort modes, `Direct ATS` vs `Career Board Role` badges, single sticky toolbar, sticky table headers, collapsible mobile filter drawer, dynamic company filter & Candidate Profile drawer, accurate KPI counts, `escapeHtml` XSS escaping, Status Export/Import JSON).
  - **Phase 4:** Fixed silent `except Exception: pass` in `scripts/sync_tracker.py` (added `REPO_ROOT` to `sys.path`, structured logging, non-zero exit); created `scripts/run_pipeline.py` (`--dry-run` default, `--send` opt-in); created `.github/workflows/job_hunt_pipeline.yml` (Mondays & Thursdays 9:00 AM IST + `workflow_dispatch`).

---

## 2. Completed in Phase 5 (2026-11-28)

All pending steps from Section 2 have been executed and committed.

1. ✅ **`data/target_companies.json` ATS metadata** (77 total companies):
   - **Boeing India** — added `workday_tenant: "boeing"`, `workday_site: "EXTERNAL_CAREERS"`, `careers_url` and `feed_url` pointing to `boeing.wd1.myworkdayjobs.com`.
   - **Acron Aviation** — new entry: `ats_type: "lever"`, `lever_site: "acronaviation"`, `tier: "Enterprise / OEM"`, `relevance: 5`, Bengaluru confirmed.
   - **Airbound** — new entry: `ats_type: "ashby"`, `board_token: "airbound"`, `tier: "Startup / Emerging"`, `relevance: 4`, Bengaluru confirmed.

2. ✅ **`tests/test_verify_links.py`** — 54 mocked unit tests:
   - `classify_url_type` for Lever/Ashby/Greenhouse/Workday/Kula/Freshteam/board-anchor patterns.
   - `_check_ats_api_direct`: Lever and Greenhouse API 200/404/410.
   - `check_url_health`: HTTP 429 → `rate_limited` (never `expired`), soft-404, 403/999 restricted, board CTA dual-check.
   - `verify_board_role_cta`: title+CTA with token-level fallback, HTML entity decoding.
   - `verify_all_openings`: metadata persistence, rate_limited counter, skip_inactive flag.
   - `ingest_openings` URL-type gate: `generic_portal` rejected, `direct_requisition` accepted.

3. ✅ **`tests/test_linkedin_ingest.py`** — 50 mocked unit tests:
   - `normalize_linkedin_id`, `extract_linkedin_job_id` (URL path/querystring).
   - `check_safety_signals`: HTTP 999, CAPTCHA, authwall, checkpoint — all halt immediately.
   - Daily view counter: 40/day cap, next-day reset, `viewed_ids` deduplication.
   - `_is_duplicate_of_existing`: by ID/req_id/URL/company+title.
   - `_save_raw_jd`: creates `applications/<id>/jd_raw.txt`, rejects empty/whitespace.
   - `load_bookmarklet_json`: single-dict, list, nested-jobs-key, filters non-dicts.
   - `capture_from_local_cdp`: non-localhost rejected, CAPTCHA title halts, LinkedIn tab captured.
   - `ingest_linkedin_records` dry-run: low-fit skipped, duplicate skipped, CAPTCHA halts, `saved_jds == []` in dry-run.
   - `main()` CLI: exit code 0 no records, exit code 2 on safety halt.

4. ✅ **`tests/test_run_pipeline.py`** — 17 mocked unit tests:
   - `run_pipeline()` dry-run: all 5 stages called, `tracker_synced=True`, `site_rebuilt=True`, `email_dispatched=False`.
   - `skip_discovery`/`skip_verify` flags bypass respective stages.
   - `sync_json_to_markdown` and `build_site` always called.
   - Missing companies file raises `FileNotFoundError`.
   - `send_email=True` with unnotified roles dispatches email.
   - `main()` CLI: `--dry-run`, `--send`, `--skip-*` flags, exit code 1 on critical failure.

5. ✅ **End-to-End Verification**:
   - `pytest -v` → **244 passed, 0 failed** (106 prior + 138 new tests).
   - `run_pipeline.py --dry-run --skip-discovery --skip-verify` → exit 0:
     - `tracker_synced: true`, `site_rebuilt: true`, `dry_run: true`
     - 46 total / 21 active roles, all three files (`openings.json`, `Openings_Tracker.md`, `docs/index.html`) 100% synchronized.

---

## 3. One-Time Manual Operator Setup
- **GitHub Actions permissions:** In GitHub repo **Settings → Actions → General → Workflow permissions**, enable **Read and write permissions** so `.github/workflows/job_hunt_pipeline.yml` can commit updated `data/` and `docs/index.html`.
- **GitHub Pages:** In **Settings → Pages**, set Source to **Deploy from a branch** → `main` → `/docs`.
- **LinkedIn Bookmarklet:** Create a Chrome bookmark whose URL is the `javascript:(function(){...})();` snippet from `scripts/linkedin_bookmarklet.js`. Click it on any LinkedIn job page to download the JSON capture, then run `python3 scripts/linkedin_ingest.py --from-json <downloaded-file.json>`.

---

## 4. Copy-Paste Agent Prompt

```markdown
Read `docs/HANDOFF_PENDING_STEPS.md` and `GEMINI.md` in `/Users/gp/Desktop/GP Github Local/Mansi Job Hunt`, then execute all pending repository steps in Section 2:

1. Update `data/target_companies.json` for Boeing India (Workday), Acron Aviation (Lever), and Airbound (Ashby).
2. Create `tests/test_verify_links.py` with mocked HTTP/ATS/CTA tests.
3. Create `tests/test_linkedin_ingest.py` covering Bookmarklet JSON, local CDP, 40/day cap, CAPTCHA/999 halt, deduplication, and `jd_raw.txt` saving.
4. Add unit test coverage for `scripts/run_pipeline.py`.
5. Run `/Library/Frameworks/Python.framework/Versions/3.12/bin/pytest -v` (confirm 0 failures) and `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 scripts/run_pipeline.py --dry-run` (confirm `data/openings.json`, `data/Openings_Tracker.md`, and `docs/index.html` are 100% synchronized).

Never auto-scrape LinkedIn via `requests`/`urllib` or send real emails (`--dry-run` only).
```
