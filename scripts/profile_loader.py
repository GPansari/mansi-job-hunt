"""Verified Master Candidate Dossier & Profile Loader.

Loads canonical candidate metadata (`profile/candidate.json`), the verified
master dossier (`profile/master_dossier.md`), and resume PDF text without
adding third-party dependencies so downstream tailoring and interview-prep
modules can ground every generated claim in verified facts.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANDIDATE_PATH = Path("profile/candidate.json")
DEFAULT_DOSSIER_PATH = Path("profile/master_dossier.md")

_H2_PATTERN = re.compile(r"^##(?!#)\s+(.+?)\s*$")
_BULLET_PATTERN = re.compile(r"^[-*]\s+(.+?)\s*$")


def _resolve_existing_path(path: Path | str) -> Path:
    """Resolve a path directly or relative to REPO_ROOT, raising if missing."""
    candidate = Path(path)
    if candidate.exists():
        return candidate
    if not candidate.is_absolute():
        repo_candidate = REPO_ROOT / candidate
        if repo_candidate.exists():
            return repo_candidate
    raise FileNotFoundError(f"Required file not found: {candidate}")


def _extract_pdf_text_pypdf(resolved: Path) -> str:
    """Pure-Python PDF text extraction fallback using `pypdf`."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PDF text extraction requires `pdftotext` on PATH or the `pypdf` package."
        ) from exc

    reader = PdfReader(str(resolved))
    pages_text: list[str] = []
    for page in reader.pages:
        pages_text.append(page.extract_text() or "")
    return "\x0c".join(pages_text)


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract plain text from a PDF file using `pdftotext` with a pure-Python `pypdf` fallback."""
    resolved = _resolve_existing_path(pdf_path)
    try:
        result = subprocess.run(
            ["pdftotext", str(resolved), "-"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return _extract_pdf_text_pypdf(resolved)


def parse_dossier_sections(dossier_markdown: str) -> dict[str, str]:
    """Split a markdown dossier on `## <Heading>` lines into heading->body."""
    sections: dict[str, str] = {}
    current_heading: str | None = None
    buffer: list[str] = []

    for line in dossier_markdown.splitlines():
        match = _H2_PATTERN.match(line)
        if match:
            if current_heading is not None:
                sections[current_heading] = "\n".join(buffer).strip()
            current_heading = match.group(1)
            buffer = []
        elif current_heading is not None:
            buffer.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(buffer).strip()

    return sections


def _extract_bullets(section_text: str) -> list[str]:
    """Collect stripped bullet item texts (`- ...` or `* ...`) from a section."""
    items: list[str] = []
    for line in section_text.splitlines():
        match = _BULLET_PATTERN.match(line.strip())
        if match:
            item = match.group(1).strip()
            if item:
                items.append(item)
    return items


def _dedupe_preserve_case(items: list[str]) -> list[str]:
    """Deduplicate strings case-insensitively while preserving first-seen case."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        item = raw.strip()
        if not item:
            continue
        key = item.casefold()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def extract_verified_facts(
    dossier_markdown: str,
    candidate: dict[str, Any],
) -> dict[str, list[str]]:
    """Extract categorized verified facts from dossier markdown and candidate JSON."""
    sections = parse_dossier_sections(dossier_markdown)

    core_skills = [
        str(skill) for skill in candidate.get("core_skills", []) if str(skill).strip()
    ]
    raw_education = candidate.get("education")
    candidate_education: list[str]
    if isinstance(raw_education, list):
        candidate_education = [str(item) for item in raw_education if str(item).strip()]
    elif isinstance(raw_education, str) and raw_education.strip():
        candidate_education = [raw_education.strip()]
    else:
        candidate_education = []

    return {
        "companies": _dedupe_preserve_case(
            _extract_bullets(sections.get("Verified Companies", ""))
        ),
        "programs": _dedupe_preserve_case(
            _extract_bullets(sections.get("Verified Programs", ""))
        ),
        "standards": _dedupe_preserve_case(
            _extract_bullets(sections.get("Verified Standards", ""))
        ),
        "skills_and_tools": _dedupe_preserve_case(
            _extract_bullets(sections.get("Verified Skills & Tools", "")) + core_skills
        ),
        "metrics": _dedupe_preserve_case(
            _extract_bullets(sections.get("Verified Metrics", ""))
        ),
        "education": _dedupe_preserve_case(
            _extract_bullets(sections.get("Education", "")) + candidate_education
        ),
        "experience": _dedupe_preserve_case(
            _extract_bullets(sections.get("Experience", ""))
        ),
        "target_scope": _dedupe_preserve_case(
            _extract_bullets(sections.get("Target Scope & Deal-Breakers", ""))
        ),
    }


def load_master_profile(
    candidate_path: Path = DEFAULT_CANDIDATE_PATH,
    dossier_path: Path = DEFAULT_DOSSIER_PATH,
) -> dict[str, Any]:
    """Load candidate JSON, master dossier markdown, parsed sections, and verified facts."""
    resolved_candidate = _resolve_existing_path(candidate_path)
    resolved_dossier = _resolve_existing_path(dossier_path)

    candidate = json.loads(resolved_candidate.read_text(encoding="utf-8"))
    dossier_markdown = resolved_dossier.read_text(encoding="utf-8")
    sections = parse_dossier_sections(dossier_markdown)
    verified_facts = extract_verified_facts(dossier_markdown, candidate)

    return {
        "candidate": candidate,
        "dossier_markdown": dossier_markdown,
        "sections": sections,
        "verified_facts": verified_facts,
    }
