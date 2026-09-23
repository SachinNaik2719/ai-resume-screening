"""Rule-based field extraction: sections, contact details, skills, projects.

No LLM here — extraction must be deterministic and cheap; the LLM is only
consulted later for quality judgment (scoring), never for hard filtering.
"""
from __future__ import annotations

import re

from .keywords import SECTION_PATTERNS
from .models import ExtractedInfo, Project

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{2,5}(?:[\s.-]\d{1,5}){1,3}(?!\w)"
)
GITHUB_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}[A-Za-z0-9])?)"
    r"|github\.com/([A-Za-z0-9][\w-]{0,38})|\bgit\s?hub\s*[:@]\s*([A-Za-z0-9][\w-]{0,38})",
    re.I,
)
LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w-]+", re.I)

BULLET_RE = re.compile(r"^\s*(?:[-•*▪●>]+|\d+[.)])\s*")

# Words that look like a section heading if they appear alone on a line and
# match a known section pattern.
MAX_HEADING_LEN = 45


def split_sections(text: str) -> dict[str, str]:
    """Split resume text into canonical sections by recognising heading lines.

    Returns at least a ``header`` key (text before the first heading).
    Resume layouts vary wildly, so unknown headings become their own keys —
    downstream logic only reads keys it knows about.
    """
    lines = text.splitlines()
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    current_key = ""
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) <= MAX_HEADING_LEN and not BULLET_RE.match(line):
            matched_key = None
            for key, pattern in SECTION_PATTERNS:
                if pattern.match(stripped.rstrip(":")):
                    matched_key = key
                    break
            if matched_key:
                # flush into canonical key; merge duplicates (e.g. two skill blocks)
                if matched_key in sections:
                    current = matched_key
                else:
                    sections[matched_key] = []
                    current = matched_key
                current_key = matched_key
                continue
        sections[current].append(line)
    return {key: "\n".join(body).strip() for key, body in sections.items()}


_NAME_LABEL_RE = re.compile(r"^\s*(?:name|candidate)\s*[:\-]\s*(.+)$", re.I | re.M)
_SECTION_WORD_RE = re.compile(
    r"^(?:summary|skills?|education|experience|projects?|contact|details|"
    r"personal|address|languages?|declaration|certifications?|interests?)$",
    re.I,
)
_CONTACT_LABEL_RE = re.compile(
    r"email|e-mail|phone|mobile|address|linkedin|github|www\.|http", re.I
)


def _looks_like_name(candidate: str, *, strict: bool) -> bool:
    """Shared validity check for name candidates.

    ``strict=True`` is used for lines discovered near the email (fallback):
    real name lines are short, capitalized, digit-free and not sentences.
    """
    candidate = candidate.strip()
    if not candidate or len(candidate) > 60:
        return False
    words = candidate.split()
    if not 1 <= len(words) <= 6:
        return False
    if _CONTACT_LABEL_RE.search(candidate) or "@" in candidate:
        return False
    if _SECTION_WORD_RE.match(candidate.strip(" :.-")):
        return False
    if any(ch.isdigit() for ch in candidate):
        return False
    # Sentence-like lines are prose, never names.
    if candidate.endswith(".") and len(words) >= 4:
        return False
    if not any(ch.isalpha() for ch in candidate):
        return False
    if strict:
        if len(words) < 2:
            return False
        if not candidate[0].isupper():
            return False
        # Every word should be a name-ish token: capitalized, initial, or
        # short connector (de, van, bin ...).
        for word in words:
            bare = word.strip(".,")
            if not bare:
                return False
            if bare.isupper() and len(bare) > 1:      # PRIYA, R, K R
                continue
            if bare[0].isupper():                      # Sumaiya, H., S.
                continue
            if bare.lower() in {"de", "van", "der", "bin", "ibn", "al", "la"}:
                continue
            return False
    else:
        # Loose pass: first line heuristics — mostly capitalized words.
        if not all(w[0].isupper() or w.lower() in {"de", "van", "der", "bin"}
                   for w in words if w):
            return False
    return True


def _name_from_email_line(line: str) -> str | None:
    """Handle 'Name <x@y.z>' style lines: keep the part before the email."""
    head, sep, _ = line.partition("@")
    if not sep:
        return None
    # Cut at label words before the email local part, then drop trailing
    # digit-bearing handle tokens glued to the name.
    head = re.split(r"\b(?:email|e-mail|mail)\b[:\s]*", head, flags=re.I)[-1]
    head = head.replace("|", " ").strip(" ,;<")
    tokens = [t for t in head.split() if t]
    while tokens and (any(c.isdigit() for c in tokens[-1]) or "@" in tokens[-1]):
        tokens.pop()
    name = " ".join(tokens)
    return name if _looks_like_name(name, strict=False) else None


def _extract_name(header: str, sections: dict[str, str], full_text: str = "") -> str:
    # 1. Explicit label anywhere in the document: "Name: Jane Doe"
    labeled = _NAME_LABEL_RE.search(full_text or header)
    if labeled and _looks_like_name(labeled.group(1), strict=False):
        return labeled.group(1).strip()

    lines = [line for line in (full_text or header).splitlines() if line.strip()]

    # 2. Header first-pass: standalone name line, or name glued to an email.
    for line in lines[:15]:
        stripped = line.strip()
        if "@" in stripped:
            glued = _name_from_email_line(stripped)
            if glued:
                return glued
            continue
        if re.match(r"^(?:curru?ent|seeking|aspiring)\b", stripped, re.I):
            continue
        if _looks_like_name(stripped, strict=False):
            return stripped
        if len(stripped.split()) <= 4 and _looks_like_name(stripped, strict=True):
            return stripped

    # 3. Fallback: names in real resumes often sit right next to the email
    #    (contact block after the summary, or above the address).
    email_index = next(
        (i for i, line in enumerate(lines) if EMAIL_RE.search(line)), None
    )
    if email_index is not None:
        for offset in (-3, -2, -1, 1, 2, 3):
            index = email_index + offset
            if 0 <= index < len(lines):
                stripped = lines[index].strip()
                if _looks_like_name(stripped, strict=True):
                    return stripped

    # 4. Give up cleanly; caller falls back to the filename.
    return ""


def extract_skills(skills_text: str) -> list[str]:
    """Split a skills section into individual skill tokens."""
    if not skills_text:
        return []
    # Split on bullets/newlines first, then on separators inside each chunk.
    raw_items: list[str] = []
    for line in skills_text.splitlines():
        line = BULLET_RE.sub("", line).strip()
        if not line:
            continue
        # Drop "Languages:" style prefixes but keep the values.
        parts = re.split(r"(?<=[\w)\]])\s*[,;|/•·]\s*|\s+\|\s+", line)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if re.match(r"^[A-Za-z&/+\-. ]{1,30}$", part) and ":" in part:
                _, _, values = part.partition(":")
                raw_items.extend(re.split(r"\s*[,;|/]\s*", values))
            else:
                raw_items.append(part)
    skills: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        item = re.sub(r"\s{2,}", " ", item).strip(" -–—:|/·•")
        if not item or len(item) > 60:
            continue
        # Skill lines are typically short phrases; reject full sentences.
        if item.endswith(".") and len(item.split()) > 6:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        skills.append(item)
    return skills


def extract_projects(projects_text: str, experience_text: str = "") -> list[Project]:
    """Heuristic project extraction: heading-like lines + their bullet blurbs."""
    projects: list[Project] = []
    current: Project | None = None
    for line in projects_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if BULLET_RE.match(line):
            blurb = BULLET_RE.sub("", stripped)
            if current is None:
                current = Project(title="", description=blurb)
                projects.append(current)
            else:
                current.description = f"{current.description} {blurb}".strip()
        else:
            # A non-bullet line starts a new project (its "title").
            title = stripped.rstrip(":")
            current = Project(title=title, description="")
            projects.append(current)
    # Fallback: treat bullet lines in experience as projects if none found.
    if not projects and projects_text.strip():
        projects.append(Project(title="", description=projects_text.strip()))
    return projects


def _project_summary(projects: list[Project], max_len: int = 220) -> str:
    for project in projects:
        text = f"{project.title} — {project.description}".strip(" —")
        text = re.sub(r"\s+", " ", text)
        if text:
            return text[:max_len].rstrip() + ("…" if len(text) > max_len else "")
    return ""


def extract_candidate_info(parsed_text: str) -> ExtractedInfo:
    """Run every rule-based extractor over raw resume text."""
    sections = split_sections(parsed_text)
    header = sections.get("header", "")

    email_match = EMAIL_RE.search(parsed_text)
    phone_match = PHONE_RE.search(parsed_text)
    github_url = None
    gh = GITHUB_RE.search(parsed_text)
    if gh:
        username = next((g for g in gh.groups() if g), None)
        if username:
            github_url = f"https://github.com/{username}"

    skills = extract_skills(sections.get("skills", ""))

    info = ExtractedInfo(
        name=_extract_name(header, sections, parsed_text),
        email=email_match.group(0) if email_match else None,
        phone=phone_match.group(0).strip() if phone_match else None,
        github_url=github_url,
        skills=skills,
        sections=sections,
        projects=extract_projects(
            sections.get("projects", ""), sections.get("experience", "")
        ),
    )
    info.summary = _project_summary(info.projects)
    return info
