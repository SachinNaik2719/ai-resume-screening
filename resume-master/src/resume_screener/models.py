"""Typed data models shared across the pipeline (Pydantic v2).

These double as the structured-output contract for LLM calls and the JSON
serialization contract for results.json.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Parsing / extraction
# --------------------------------------------------------------------------- #
class ParsedResume(BaseModel):
    """Raw outcome of reading one file from the input directory."""

    path: str
    filename: str
    format: str  # pdf | docx | txt | unknown
    sha256: str = ""
    text: str = ""
    parse_error: Optional[str] = None

    @property
    def parsed_ok(self) -> bool:
        return self.parse_error is None and bool(self.text.strip())


class Project(BaseModel):
    title: str = ""
    description: str = ""


class ExtractedInfo(BaseModel):
    """Structured candidate fields derived by rule-based parsing."""

    name: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    github_url: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    sections: dict[str, str] = Field(default_factory=dict)  # canonical -> text
    projects: list[Project] = Field(default_factory=list)
    summary: str = ""  # short one-liner used in output


# --------------------------------------------------------------------------- #
# Eligibility (hard filter — always rule-based, never LLM)
# --------------------------------------------------------------------------- #
class EligibilityResult(BaseModel):
    candidate: str = ""
    filename: str = ""
    eligible: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    python_evidence: list[str] = Field(default_factory=list)
    ai_evidence: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
class ScoreBreakdown(BaseModel):
    """Five rubric categories + penalty. The five keys are fixed by spec."""

    ai_project_depth: int = 0
    python_backend: int = 0
    cloud_fullstack: int = 0
    github: int = 0
    engineering_depth: int = 0
    penalty: int = 0  # 0 or negative (spec allows extra detail beyond the 5)

    def total(self) -> int:
        base = (
            self.ai_project_depth
            + self.python_backend
            + self.cloud_fullstack
            + self.github
            + self.engineering_depth
        )
        return max(0, base + self.penalty)


class RuleScore(BaseModel):
    """Deterministic score + the evidence sentences that earned each point."""

    breakdown: ScoreBreakdown
    evidence: dict[str, list[str]] = Field(default_factory=dict)
    ai_project_count: int = 0


class LLMCategory(BaseModel):
    score: int = Field(ge=0, description="Points awarded inside the category cap")
    evidence: list[str] = Field(default_factory=list)


class LLMScore(BaseModel):
    """Structured output requested from the model (JSON-schema validated)."""

    ai_project_depth: LLMCategory
    python_backend: LLMCategory
    cloud_fullstack: LLMCategory
    engineering_depth: LLMCategory
    penalty: int = Field(default=0, ge=-15, le=0)
    penalty_reason: Optional[str] = None
    project_summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# GitHub enrichment
# --------------------------------------------------------------------------- #
GitHubStatus = Literal[
    "ok", "not_found", "rate_limited", "error", "disabled", "no_username"
]


class GitHubEnrichment(BaseModel):
    username: Optional[str] = None
    status: GitHubStatus = "no_username"
    activity_score: int = 0  # 0-5
    repo_score: int = 0  # 0-5
    summary: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)

    @property
    def score(self) -> int:
        return max(0, min(5, self.activity_score)) + max(0, min(5, self.repo_score))


# --------------------------------------------------------------------------- #
# Final per-candidate result + batch
# --------------------------------------------------------------------------- #
class CandidateResult(BaseModel):
    rank: Optional[int] = None  # null for rejected candidates
    candidate_name: str
    filename: str
    eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    total_score: int = 0
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    matched_skills: list[str] = Field(default_factory=list)
    project_summary: str = ""
    github_url: Optional[str] = None
    github_summary: Optional[str] = None
    github_enrichment_status: Optional[str] = None
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    evidence: dict[str, list[str]] = Field(default_factory=dict)
    scoring_method: Literal["rule_based", "hybrid_llm"] = "rule_based"
    errors: list[str] = Field(default_factory=list)  # e.g. llm/github failures


class BatchSummary(BaseModel):
    total_files: int = 0
    parsed_ok: int = 0
    parse_failures: int = 0
    duplicates_skipped: int = 0
    unsupported_files: int = 0
    eligible: int = 0
    rejected: int = 0
    github_enriched: int = 0
    github_failures: int = 0
    llm_calls_ok: int = 0
    llm_calls_failed: int = 0
    scoring_method: Literal["rule_based", "hybrid_llm"] = "rule_based"


class ResultsFile(BaseModel):
    generated_at: str = ""
    input_dir: str = ""
    batch_summary: BatchSummary
    results: list[CandidateResult]
    rejected: list[EligibilityResult]
