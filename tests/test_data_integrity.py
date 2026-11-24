import json
from pathlib import Path

def test_candidate_profile_schema():
    candidate_file = Path("profile/candidate.json")
    assert candidate_file.exists(), "profile/candidate.json must exist"
    data = json.loads(candidate_file.read_text())
    assert data["name"] == "Mansi Agrawal"
    assert data["email"] == "agrawal.mansi20@gmail.com"
    assert "MBSE" in data["core_skills"]
    assert "SysML" in data["core_skills"]
    assert len(data["target_titles"]) > 0
    assert data["experience_years"] >= 10
    assert "Bangalore" in data["location"]
    assert "target_locations" in data and len(data["target_locations"]) > 0
    assert "target_domains" in data and len(data["target_domains"]) > 0
    assert "excluded_keywords" in data and len(data["excluded_keywords"]) > 0

def test_target_companies_schema():
    companies_file = Path("data/target_companies.json")
    assert companies_file.exists(), "data/target_companies.json must exist"
    data = json.loads(companies_file.read_text())
    assert len(data) >= 60, f"Expected at least 60 target companies, found {len(data)}"
    
    valid_ats_types = {"workday", "greenhouse", "lever", "freshteam", "kula", "ashby", "custom"}
    for company in data:
        assert "name" in company and company["name"], "Company name must not be empty"
        assert "relevance" in company and 1 <= company["relevance"] <= 5, f"Invalid relevance in {company.get('name')}"
        assert "careers_url" in company, f"Missing careers_url in {company.get('name')}"
        assert company["careers_url"].startswith("http")
        assert " " not in company["careers_url"], f"careers_url must start with http in {company.get('name')}"
        assert company.get("ats_type") in valid_ats_types, f"Invalid ats_type in {company.get('name')}"
        assert "tier" in company, f"Missing tier in {company.get('name')}"

def test_openings_schema():
    openings_file = Path("data/openings.json")
    assert openings_file.exists(), "data/openings.json must exist"
    data = json.loads(openings_file.read_text())
    assert len(data) >= 20, f"Expected at least 20 active openings, found {len(data)}"
    
    valid_statuses = {"Not Applied", "Applied", "Screening", "Interview", "Offer", "Rejected", "Watching", "Needs Review", "Inactive Posting"}
    seen_ids = set()
    for op in data:
        assert "id" in op and op["id"], "Opening ID must not be empty"
        assert op["id"] not in seen_ids, f"Duplicate opening ID: {op['id']}"
        seen_ids.add(op["id"])
        
        assert "company" in op and op["company"]
        assert "title" in op and op["title"]
        assert "fit_score" in op and 1 <= op["fit_score"] <= 5
        assert op["status"] in valid_statuses, f"Invalid status {op.get('status')} in {op.get('id')}"
        assert "apply_url" in op and op["apply_url"].startswith("http")
        assert "skills_matched" in op and isinstance(op["skills_matched"], list)
        assert "date_discovered" in op
        assert "last_updated" in op

def test_directory_reorganization_and_file_moves():
    resume_path = Path("profile/Mansi_Agrawal_Resume.pdf")
    assert resume_path.exists(), "Resume must exist at profile/Mansi_Agrawal_Resume.pdf"
    assert not Path("Mansi Agrawal Resume.pdf").exists(), "Old resume in root should be removed"

    archive_excel = Path("archive/legacy_excel")
    archive_docs = Path("archive/legacy_docs")
    assert archive_excel.exists() and archive_excel.is_dir()
    assert archive_docs.exists() and archive_docs.is_dir()

    # Verify no .xlsx or .docx files remain in root
    assert len(list(Path(".").glob("*.xlsx"))) == 0, "No .xlsx should remain in root"
    assert len(list(Path(".").glob("*.docx"))) == 0, "No .docx should remain in root"

    # Verify files exist in archive
    assert len(list(archive_excel.glob("*.xlsx"))) >= 3
    assert len(list(archive_docs.glob("*.docx"))) >= 1
