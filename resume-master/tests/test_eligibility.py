"""Eligibility hard-filter tests — the highest-weight rubric area (25%)."""
from __future__ import annotations

from resume_screener.eligibility import check_eligibility


def test_strong_candidate_is_eligible(strong_info):
    verdict = check_eligibility(strong_info, "a.pdf")
    assert verdict.eligible is True
    assert verdict.rejection_reasons == []
    assert verdict.python_evidence
    assert verdict.ai_evidence


def test_python_only_profile_rejected(no_ai_info):
    verdict = check_eligibility(no_ai_info, "b.pdf")
    assert verdict.eligible is False
    assert "No AI/agentic project evidence" in verdict.rejection_reasons
    assert "No evidence of Python stack" not in verdict.rejection_reasons
    # matched skills still reported for debugging
    assert any("Python" in s for s in verdict.matched_skills)


def test_non_python_profile_rejected(no_python_info):
    verdict = check_eligibility(no_python_info, "c.pdf")
    assert verdict.eligible is False
    assert "No evidence of Python stack" in verdict.rejection_reasons


def test_js_react_alone_never_eligible(no_python_info):
    """A polished JS/React resume must not pass on writing quality alone."""
    verdict = check_eligibility(no_python_info, "d.pdf")
    assert verdict.eligible is False
    assert len(verdict.rejection_reasons) == 2


def test_python_plus_js_ai_still_eligible(strong_info):
    """Extra JS/React skills must not cause rejection when Python+AI present."""
    strong_info.skills.append("React")
    strong_info.skills.append("Next.js")
    verdict = check_eligibility(strong_info, "e.pdf")
    assert verdict.eligible is True


def test_ai_keyword_in_summary_only_is_not_enough():
    """Generic 'AI' in the objective prose should not pass the AI filter."""
    from resume_screener.extraction import extract_candidate_info

    text = """
Sam Lee
sam@email.com

SUMMARY
Aspiring engineer who loves AI and building things.

SKILLS
Python, Flask, PostgreSQL

PROJECTS
- REST API for a blog with auth and caching in Flask.
"""
    verdict = check_eligibility(extract_candidate_info(text), "f.pdf")
    assert verdict.eligible is False
    assert "No AI/agentic project evidence" in verdict.rejection_reasons


def test_ai_framework_in_skills_counts_as_evidence():
    from resume_screener.extraction import extract_candidate_info

    text = """
Dana Wu
dana@email.com

SKILLS
Python, LangChain, LlamaIndex, RAG, embeddings

PROJECTS
- Knowledge-base search tool using LangChain retrieval over internal docs.
"""
    verdict = check_eligibility(extract_candidate_info(text), "g.pdf")
    assert verdict.eligible is True
