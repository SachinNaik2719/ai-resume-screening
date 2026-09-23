"""Extraction tests: sections, contact fields, skills, projects."""
from __future__ import annotations

from resume_screener.extraction import (
    extract_candidate_info,
    extract_skills,
    split_sections,
)

RESUME = """Asha Rao
SDE Intern | asha.rao@email.com | +91 98123 45678
github.com/coderao | linkedin.com/in/asha-rao

SUMMARY
Builder of things.

TECHNICAL SKILLS
Languages: Python, SQL, TypeScript
Tools: Docker, Git, pytest, FastAPI

WORK EXPERIENCE
- Backend Intern at Finlytics: built FastAPI services.

PERSONAL PROJECTS
Stateful RAG Assistant
- Multi-agent workflow with LangGraph and retrieval.
Other Tools
- Small CLI utilities in Python.

EDUCATION
B.Tech Computer Science, 2025
"""


def test_sections_are_split_by_heading():
    sections = split_sections(RESUME)
    assert "header" in sections
    assert "skills" in sections
    assert "experience" in sections
    assert "projects" in sections
    assert "education" in sections
    # Headings themselves are consumed, not left in body text
    assert not sections["education"].strip().lower().startswith("education")
    # Summary heading maps to canonical 'summary'
    assert "summary" in sections


def test_contact_fields_extracted():
    info = extract_candidate_info(RESUME)
    assert info.name == "Asha Rao"
    assert info.email == "asha.rao@email.com"
    assert info.github_url == "https://github.com/coderao"
    assert info.phone is not None


def test_skills_extraction_handles_prefixes():
    info = extract_candidate_info(RESUME)
    lowered = [s.lower() for s in info.skills]
    assert any("python" in s for s in lowered)
    assert any("docker" in s for s in lowered)
    assert any("fastapi" in s for s in lowered)


def test_projects_extracted_with_titles():
    info = extract_candidate_info(RESUME)
    titles = [p.title for p in info.projects]
    assert any("RAG" in t for t in titles)
    assert info.summary, "project summary should be populated"


def test_extract_skills_robust_to_layouts():
    assert extract_skills("") == []
    assert extract_skills("Python, FastAPI, | Redis \n- Docker") == [
        "Python", "FastAPI", "Redis", "Docker"
    ]


def test_missing_fields_do_not_crash():
    info = extract_candidate_info("just some random text with no structure")
    assert info.email is None
    assert info.github_url is None
    assert info.skills == []
    # Unstructured text yields no invented name; caller falls back to filename.
    assert info.name == ""
    from resume_screener.eligibility import check_eligibility
    verdict = check_eligibility(info, "candidate_07.pdf")
    assert verdict.candidate == "candidate 07"


def test_name_glued_to_email_is_split():
    text = """Sumaiya Sultana Shaiksultanasumaiya623@gmail.com | +91 97015 28467
GitHub - LinkedIn Hyderabad, India

SKILLS
Python, FastAPI

PROJECTS
- AI bot using LangChain retrieval.
"""
    info = extract_candidate_info(text)
    assert info.name == "Sumaiya Sultana"
    assert info.email == "Shaiksultanasumaiya623@gmail.com"


def test_name_found_next_to_contact_block():
    """Real resumes often put the contact block before/after the name."""
    text = """SUMMARY
Motivated engineer eager to contribute to innovative projects.

Email: priyaraguraman29@gmail.com | Mobile: 9384452444 | Vellore, India.
LinkedIn: www.linkedin.com/in/priya-r
PRIYA R

SKILLS
Python, Django
"""
    info = extract_candidate_info(text)
    assert info.name == "PRIYA R"

    text2 = """deploying AI applications using Hugging Face. Passionate about scalable systems.
learning modern ML technologies.
MANOJ KUMAR K R
manojkumar.k.r0904@gmail.com , +91 7090404953,

SKILLS
Python
"""
    info2 = extract_candidate_info(text2)
    assert info2.name == "MANOJ KUMAR K R"
