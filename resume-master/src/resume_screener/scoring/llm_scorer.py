"""LLM-assisted scoring: structured judgment blended over the rule baseline.

Contract:
  * Hard eligibility is NEVER decided here (stays in eligibility.py).
  * The model sees only eligible candidates and returns LLMScore (Pydantic).
  * Category scores are clamped to the rubric caps; blend weight from config.
  * Any model failure falls back to the pure rule score for that candidate.
"""
from __future__ import annotations

import re

from ..config import SCORE_MAX, Settings
from ..models import (
    EligibilityResult,
    ExtractedInfo,
    LLMScore,
    RuleScore,
    ScoreBreakdown,
)
from .llm_client import LLMClient, LLMOutcome

MAX_RESUME_CHARS = 12000  # keep prompts bounded and costs predictable


def build_prompt(info: ExtractedInfo, eligibility: EligibilityResult) -> str:
    sections = info.sections or {}
    resume_text = "\n\n".join(
        f"## {key.upper()}\n{value}" for key, value in sections.items() if value
    )
    resume_text = resume_text[:MAX_RESUME_CHARS]

    return f"""Screen this candidate for an SDE intern role (Python + AI/agentic systems).

Category caps: ai_project_depth={SCORE_MAX['ai_project_depth']},
python_backend={SCORE_MAX['python_backend']},
cloud_fullstack={SCORE_MAX['cloud_fullstack']},
engineering_depth={SCORE_MAX['engineering_depth']}.
Penalty: integer from -15 to 0 for thin LLM/API-wrapper projects or
tutorial-style projects without implementation detail.

Rules:
- Award points for EVIDENCE in projects/internships over skill-list keywords.
- AI depth rewards real systems: agents, RAG, retrieval, state, orchestration,
  evaluation, data processing, backend integration — not bare API calls.
- If an "AI project" is only a thin wrapper around an LLM/API call with no
  workflow, data processing, retrieval, state, evaluation, or product logic,
  apply a penalty (-5 to -15) and say why in penalty_reason.
- python_backend rewards Python, FastAPI, async, PostgreSQL, Redis, testing.
- cloud_fullstack rewards GCP/Docker/deployment; React/Next.js count only as
  supporting signals of an end-to-end system.
- engineering_depth: testing, architecture, caching, queues, observability,
  concurrency, failure handling (max {SCORE_MAX['engineering_depth']}).
- strengths/concerns: 2-4 short bullets each, grounded in the resume.
- project_summary: one sentence describing the strongest AI project.

Hard filter already passed: {eligibility.rejection_reasons or 'eligible'}
Matched skills: {', '.join(eligibility.matched_skills[:30])}

RESUME:
{resume_text}

Return ONLY a JSON object with keys:
ai_project_depth, python_backend, cloud_fullstack, engineering_depth
(each: {{"score": <int>, "evidence": ["<quote or short reason>", ...]}}),
penalty (int), penalty_reason (string|null), project_summary (string),
strengths (array of strings), concerns (array of strings)."""


def _clamp(category: str, value: int) -> int:
    return max(0, min(int(value), SCORE_MAX[category]))


def blend_scores(
    rule: RuleScore,
    llm: LLMScore | None,
    settings: Settings,
) -> tuple[ScoreBreakdown, dict[str, list[str]], str]:
    """Combine rule baseline with LLM judgment.

    Returns (breakdown, evidence, method). GitHub points are injected by the
    caller before or after — this function only blends the non-GitHub parts.
    """
    w = settings.llm_blend_weight if llm is not None else 0.0
    rb = rule.breakdown
    evidence = dict(rule.evidence)

    if llm is None:
        return rb, evidence, "rule_based"

    blended = ScoreBreakdown(
        ai_project_depth=_clamp(
            "ai_project_depth",
            round((1 - w) * rb.ai_project_depth + w * llm.ai_project_depth.score),
        ),
        python_backend=_clamp(
            "python_backend",
            round((1 - w) * rb.python_backend + w * llm.python_backend.score),
        ),
        cloud_fullstack=_clamp(
            "cloud_fullstack",
            round((1 - w) * rb.cloud_fullstack + w * llm.cloud_fullstack.score),
        ),
        github=rb.github,
        engineering_depth=_clamp(
            "engineering_depth",
            round((1 - w) * rb.engineering_depth + w * llm.engineering_depth.score),
        ),
        # Keep the stricter penalty of the two judges — explainable and safe.
        penalty=min(rb.penalty, llm.penalty),
    )

    for category in ("ai_project_depth", "python_backend",
                     "cloud_fullstack", "engineering_depth"):
        llm_ev = getattr(llm, category).evidence
        if llm_ev:
            cleaned = [re.sub(r"\s+", " ", e.strip())[:140] for e in llm_ev[:4]]
            evidence[category] = evidence.get(category, []) + [
                f"[llm] {item}" for item in cleaned
            ]
    if llm.penalty_reason:
        evidence["penalty"] = evidence.get("penalty", []) + [
            f"[llm] {llm.penalty_reason[:160]}"
        ]
    return blended, evidence, "hybrid_llm"


def score_with_llm(
    info: ExtractedInfo,
    eligibility: EligibilityResult,
    rule: RuleScore,
    client: LLMClient,
    settings: Settings,
) -> tuple[ScoreBreakdown, dict[str, list[str]], str, LLMScore | None, str | None]:
    """Full scoring for one candidate. Never raises.

    Returns (breakdown, evidence, method, llm_value, error).
    """
    outcome: LLMOutcome = client.complete_json(
        build_prompt(info, eligibility), LLMScore
    )
    if not outcome.ok or not isinstance(outcome.value, LLMScore):
        breakdown, evidence, method = blend_scores(rule, None, settings)
        return breakdown, evidence, method, None, outcome.error

    breakdown, evidence, method = blend_scores(rule, outcome.value, settings)
    return breakdown, evidence, method, outcome.value, None
