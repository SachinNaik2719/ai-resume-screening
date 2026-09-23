"""Deterministic baseline scorer (100-point rubric).

Each category is scored from *evidence found in projects/experience* first and
skill-list mentions second, capped by the rubric maxima in config.SCORE_MAX.
The LLM may later adjust these numbers (see scoring/llm_scorer.py), but this
module always produces a complete, explainable score on its own.
"""
from __future__ import annotations

import re

from ..config import (
    PENALTY_MAX,
    PENALTY_MIN,
    SCORE_MAX,
    THIN_WRAPPER_PENALTY,
    TUTORIAL_PENALTY,
)
from ..keywords import (
    AI_CONTEXT_TOKENS,
    AI_DEPTH_MARKERS,
    AI_STRONG_TOKENS,
    BACKEND_TOKENS,
    CLOUD_TOKENS,
    DEPTH_TOKENS,
    THIN_WRAPPER_PATTERNS,
    TUTORIAL_PATTERNS,
)
from ..models import ExtractedInfo, RuleScore, ScoreBreakdown

# Evidence found in projects/experience is worth more than a skills-list hit:
# the rubric explicitly says "prefer evidence showing how it was used".
PROJECT_WEIGHT = 1.0
SKILLS_WEIGHT = 0.5
EXPERIENCE_WEIGHT = 0.85


def _section_weight(key: str) -> float:
    if key == "projects":
        return PROJECT_WEIGHT
    if key == "experience":
        return EXPERIENCE_WEIGHT
    return SKILLS_WEIGHT


def _weighted_hits(
    info: ExtractedInfo, tokens: dict[str, tuple[re.Pattern, int]]
) -> tuple[int, list[str]]:
    """Score token hits weighted by which resume section they appear in."""
    total = 0.0
    evidence: list[str] = []
    seen_labels: set[str] = set()
    for key in ("projects", "experience", "skills", "certifications"):
        text = info.sections.get(key, "")
        if not text:
            continue
        weight = _section_weight(key)
        for label, (pattern, points) in tokens.items():
            match = pattern.search(text)
            if match and label not in seen_labels:
                seen_labels.add(label)
                earned = points * weight
                total += earned
                evidence.append(f"[{key}] {label} (+{earned:.1f})")
    return int(round(total)), evidence


def score_python_backend(info: ExtractedInfo) -> tuple[int, list[str]]:
    points, evidence = _weighted_hits(info, BACKEND_TOKENS)
    # Python itself is a precondition of eligibility; still award base points
    # for showing Python *in projects/work*, not just in the skills list.
    base = 0
    for key in ("projects", "experience"):
        text = info.sections.get(key, "")
        if re.search(r"\bpython\b", text, re.I):
            base = 8
            evidence.append(f"[{key}] Python used in project/work (+8.0)")
            break
    if base == 0 and re.search(r"\bpython\b", info.sections.get("skills", ""), re.I):
        base = 4
        evidence.append("[skills] Python listed (+4.0)")
    score = base + points
    cap = SCORE_MAX["python_backend"]
    return min(score, cap), evidence


def score_cloud_fullstack(info: ExtractedInfo) -> tuple[int, list[str]]:
    points, evidence = _weighted_hits(info, CLOUD_TOKENS)
    cap = SCORE_MAX["cloud_fullstack"]
    return min(points, cap), evidence


def score_engineering_depth(info: ExtractedInfo) -> tuple[int, list[str]]:
    points, evidence = _weighted_hits(info, DEPTH_TOKENS)
    cap = SCORE_MAX["engineering_depth"]
    return min(points, cap), evidence


def score_ai_depth(info: ExtractedInfo) -> tuple[int, list[str], int]:
    """40 points for real AI systems: depth signals inside project prose dominate."""
    evidence: list[str] = []
    raw = 0.0

    # (1) Strong framework/implementation hits, weighted by section.
    seen: set[str] = set()
    for key in ("projects", "experience", "skills", "certifications"):
        text = info.sections.get(key, "")
        if not text:
            continue
        weight = _section_weight(key)
        for label, pattern in AI_STRONG_TOKENS.items():
            if label in seen:
                continue
            if pattern.search(text):
                seen.add(label)
                earned = 5 * weight
                raw += earned
                evidence.append(f"[{key}] {label} (+{earned:.1f})")

    # (2) Weaker ML terms only count in projects/experience.
    for key in ("projects", "experience"):
        text = info.sections.get(key, "")
        if not text:
            continue
        for label, pattern in AI_CONTEXT_TOKENS.items():
            if label in seen:
                continue
            if pattern.search(text):
                seen.add(label)
                earned = 3 * _section_weight(key)
                raw += earned
                evidence.append(f"[{key}] {label} (+{earned:.1f})")

    # (3) Depth bonus: distinct engineering markers inside AI project blocks
    #     prove the project is more than a thin API wrapper.
    ai_project_count = _count_ai_projects(info)
    depth_markers = _depth_marker_count(info)
    depth_bonus = min(15, depth_markers * 2)
    if depth_bonus:
        evidence.append(f"[projects] {depth_markers} AI-depth engineering markers (+{depth_bonus})")
    coverage_bonus = 4 if ai_project_count >= 2 else (2 if ai_project_count == 1 else 0)
    if coverage_bonus:
        evidence.append(f"[projects] {ai_project_count} AI project(s) found (+{coverage_bonus})")

    score = int(round(raw)) + depth_bonus + coverage_bonus
    cap = SCORE_MAX["ai_project_depth"]
    return min(score, cap), evidence, ai_project_count


def _ai_project_blocks(info: ExtractedInfo) -> list[str]:
    """Text blocks of projects that contain AI signals."""
    blocks: list[str] = []
    for project in info.projects:
        text = f"{project.title}\n{project.description}"
        if any(p.search(text) for p in AI_STRONG_TOKENS.values()):
            blocks.append(text)
    # Fall back to whole projects section if block splitting failed.
    if not blocks:
        section = info.sections.get("projects", "")
        if section and any(p.search(section) for p in AI_STRONG_TOKENS.values()):
            blocks.append(section)
    return blocks


def _count_ai_projects(info: ExtractedInfo) -> int:
    return len(_ai_project_blocks(info))


def _depth_marker_count(info: ExtractedInfo) -> int:
    return len({m.group(0).lower() for block in _ai_project_blocks(info)
                for m in AI_DEPTH_MARKERS.finditer(block)})


def compute_penalty(info: ExtractedInfo) -> tuple[int, list[str]]:
    """-15..0 for thin LLM wrappers and tutorial-style projects."""
    penalty = 0
    reasons: list[str] = []
    all_text = "\n".join(info.sections.get(k, "") for k in ("projects", "experience"))

    if TUTORIAL_PATTERNS.search(all_text):
        penalty += TUTORIAL_PENALTY
        reasons.append("Tutorial-style project evidence")

    thin_blocks = 0
    shallow_blocks = 0
    for block in _ai_project_blocks(info):
        if THIN_WRAPPER_PATTERNS.search(block):
            thin_blocks += 1
        elif not AI_DEPTH_MARKERS.search(block):
            shallow_blocks += 1
    if thin_blocks:
        penalty += THIN_WRAPPER_PENALTY
        reasons.append("AI project looks like a thin LLM/API wrapper")
    elif shallow_blocks and shallow_blocks >= max(1, _count_ai_projects(info)):
        penalty += -5
        reasons.append("AI project lacks implementation detail (no workflow/data/state evidence)")

    penalty = max(PENALTY_MIN, min(PENALTY_MAX, penalty))
    return penalty, reasons


def rule_score(info: ExtractedInfo) -> RuleScore:
    """Produce the full deterministic score breakdown with evidence."""
    ai_points, ai_evidence, ai_count = score_ai_depth(info)
    py_points, py_evidence = score_python_backend(info)
    cloud_points, cloud_evidence = score_cloud_fullstack(info)
    depth_points, depth_evidence = score_engineering_depth(info)
    penalty, _penalty_reasons = compute_penalty(info)

    breakdown = ScoreBreakdown(
        ai_project_depth=ai_points,
        python_backend=py_points,
        cloud_fullstack=cloud_points,
        github=0,  # filled in by GitHub enrichment stage
        engineering_depth=depth_points,
        penalty=penalty,
    )
    return RuleScore(
        breakdown=breakdown,
        evidence={
            "ai_project_depth": ai_evidence,
            "python_backend": py_evidence,
            "cloud_fullstack": cloud_evidence,
            "engineering_depth": depth_evidence,
            "penalty": _penalty_reasons,
        },
        ai_project_count=ai_count,
    )
