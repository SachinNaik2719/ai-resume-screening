"""Hard eligibility filter — deliberately rule-based and outside any LLM.

A candidate is eligible only with BOTH:
  1. Python evidence in a genuine context (skills / projects / experience), and
  2. At least one meaningful AI/LLM/RAG/agentic project, framework or
     implementation.
Other stacks (JS/Java/React) neither help nor hurt on their own.
"""
from __future__ import annotations

import re

from .keywords import (
    AI_CONTEXT_TOKENS,
    AI_STRONG_TOKENS,
    EVIDENCE_SECTIONS,
    PYTHON_RE,
)
from .models import EligibilityResult, ExtractedInfo

# Generic "AI" only counts when attached to real project/work prose.
GENERIC_AI_RE = re.compile(
    r"\b(?:ai|a\.i\.)\s+(?:project|model|system|agent|assistant|pipeline|application|driven)"
    r"|\b(?:project|system|pipeline|assistant|agent)\s+(?:using|with|based\s+on)\s+(?:an?\s+)?(?:ai|llm)\b",
    re.I,
)


def _evidence_blocks(info: ExtractedInfo) -> dict[str, str]:
    """Text of sections that count as genuine evidence (plus summary fallback)."""
    blocks = {
        key: info.sections.get(key, "")
        for key in (*EVIDENCE_SECTIONS, "certifications")
    }
    return {key: text for key, text in blocks.items() if text}


def find_python_evidence(info: ExtractedInfo) -> list[str]:
    evidence: list[str] = []
    for key, text in _evidence_blocks(info).items():
        for match in PYTHON_RE.finditer(text):
            line = _line_for(text, match.start())
            evidence.append(f"[{key}] {line}")
            break  # one hit per section is enough
    return evidence


def find_ai_evidence(info: ExtractedInfo) -> list[str]:
    """Strong AI tokens count anywhere in evidence sections; generic 'AI' or
    weak ML terms must appear inside projects/experience prose."""
    evidence: list[str] = []
    blocks = _evidence_blocks(info)
    for key, text in blocks.items():
        hits: list[str] = []
        for label, pattern in AI_STRONG_TOKENS.items():
            if pattern.search(text):
                hits.append(label)
        if key in ("projects", "experience"):
            for label, pattern in AI_CONTEXT_TOKENS.items():
                if pattern.search(text):
                    hits.append(label)
            if GENERIC_AI_RE.search(text):
                hits.append("AI project")
        if hits:
            evidence.append(f"[{key}] {', '.join(dict.fromkeys(hits))}")
    return evidence


def _line_for(text: str, pos: int) -> str:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    line = text[start:end].strip()
    return line[:160]


def _fallback_label(filename: str) -> str:
    """Readable candidate label when the resume has no extractable name."""
    stem = filename.rsplit(".", 1)[0] if filename else ""
    return stem.replace("_", " ").strip() or "Unknown Candidate"


def check_eligibility(info: ExtractedInfo, filename: str = "") -> EligibilityResult:
    matched_skills = list(info.skills)
    python_evidence = find_python_evidence(info)
    ai_evidence = find_ai_evidence(info)

    reasons: list[str] = []
    if not python_evidence:
        reasons.append("No evidence of Python stack")
    if not ai_evidence:
        reasons.append("No AI/agentic project evidence")

    return EligibilityResult(
        candidate=info.name or _fallback_label(filename),
        filename=filename,
        eligible=not reasons,
        rejection_reasons=reasons,
        matched_skills=matched_skills,
        python_evidence=python_evidence,
        ai_evidence=ai_evidence,
    )
