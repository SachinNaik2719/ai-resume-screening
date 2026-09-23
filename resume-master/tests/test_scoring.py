"""Scoring tests: caps, penalties, evidence, blending, GitHub math."""
from __future__ import annotations

from resume_screener.config import SCORE_MAX, Settings
from resume_screener.extraction import extract_candidate_info
from resume_screener.models import (
    EligibilityResult,
    GitHubEnrichment,
    LLMCategory,
    LLMScore,
    RuleScore,
    ScoreBreakdown,
)
from resume_screener.scoring.github import extract_username, _repo_score, _activity_score
from resume_screener.scoring.llm_scorer import blend_scores, score_with_llm
from resume_screener.scoring.llm_client import LLMClient
from resume_screener.scoring.rules import compute_penalty, rule_score


# ------------------------------------------------------------ rule scorer -- #
def test_all_categories_respect_caps(strong_info):
    score = rule_score(strong_info)
    b = score.breakdown
    assert 0 <= b.ai_project_depth <= SCORE_MAX["ai_project_depth"]
    assert 0 <= b.python_backend <= SCORE_MAX["python_backend"]
    assert 0 <= b.cloud_fullstack <= SCORE_MAX["cloud_fullstack"]
    assert 0 <= b.engineering_depth <= SCORE_MAX["engineering_depth"]


def test_evidence_is_produced(strong_info):
    score = rule_score(strong_info)
    assert score.evidence["ai_project_depth"], "AI points must carry evidence"
    assert score.evidence["python_backend"], "Python points must carry evidence"
    assert score.ai_project_count >= 1


def test_strong_beats_no_ai(strong_info, no_ai_info):
    strong = rule_score(strong_info)
    weak = rule_score(no_ai_info)
    assert strong.breakdown.ai_project_depth > weak.breakdown.ai_project_depth
    assert strong.breakdown.total() > weak.breakdown.total()


def test_thin_wrapper_gets_penalty(thin_wrapper_info):
    penalty, reasons = compute_penalty(thin_wrapper_info)
    assert penalty < 0
    assert reasons
    score = rule_score(thin_wrapper_info)
    assert score.breakdown.penalty < 0


def test_total_never_negative():
    b = ScoreBreakdown(ai_project_depth=0, python_backend=0, cloud_fullstack=0,
                       github=0, engineering_depth=0, penalty=-15)
    assert b.total() == 0


# ------------------------------------------------------------- blending ---- #
def _rule_for(info) -> RuleScore:
    return rule_score(info)


def test_blend_none_llm_is_pure_rule(strong_info, offline_settings):
    rule = _rule_for(strong_info)
    breakdown, _, method = blend_scores(rule, None, offline_settings)
    assert method == "rule_based"
    assert breakdown == rule.breakdown


def test_blend_hybrid_uses_llm_and_clamps(strong_info, offline_settings):
    rule = _rule_for(strong_info)
    llm = LLMScore(
        ai_project_depth=LLMCategory(score=999, evidence=["agent workflow"]),  # over cap
        python_backend=LLMCategory(score=0, evidence=[]),
        cloud_fullstack=LLMCategory(score=10, evidence=[]),
        engineering_depth=LLMCategory(score=5, evidence=[]),
        penalty=-15,
        penalty_reason="thin wrapper",
    )
    breakdown, evidence, method = blend_scores(rule, llm, offline_settings)
    assert method == "hybrid_llm"
    assert breakdown.ai_project_depth <= SCORE_MAX["ai_project_depth"]
    assert breakdown.penalty <= 0
    assert breakdown.penalty == min(rule.breakdown.penalty, -15)
    assert any(e.startswith("[llm]") for e in evidence["ai_project_depth"])


def test_llm_failure_falls_back_to_rule(strong_info, offline_settings):
    """A model failure must degrade to rule-based scoring, not raise."""
    verdict = EligibilityResult(candidate="X", eligible=True)
    rule = _rule_for(strong_info)
    client = LLMClient(offline_settings)  # not configured
    breakdown, _, method, value, error = score_with_llm(
        strong_info, verdict, rule, client, offline_settings
    )
    assert method == "rule_based"
    assert value is None
    assert error == "llm_not_configured"
    assert breakdown == rule.breakdown


# ------------------------------------------------------------ github math -- #
def test_github_username_extraction():
    assert extract_username("https://github.com/octocat") == "octocat"
    assert extract_username("https://github.com/octocat/repo") == "octocat"
    assert extract_username("http://www.github.com/a-b") == "a-b"
    assert extract_username(None) is None
    assert extract_username("https://gitlab.com/x") is None


def test_github_repo_scoring_bounds():
    score, _ = _repo_score([])
    assert score == 0
    repos = [
        {"fork": False, "pushed_at": "2026-09-01T00:00:00Z",
         "language": "Python", "topics": ["llm"], "description": "rag agent"},
        {"fork": False, "pushed_at": "2026-09-01T00:00:00Z",
         "language": "Python", "topics": [], "description": None},
        {"fork": True, "pushed_at": "2026-09-01T00:00:00Z",
         "language": "Go", "topics": [], "description": ""},
    ]
    score, _ = _repo_score(repos)
    assert 1 <= score <= 5


def test_github_activity_scoring_bounds():
    score, _ = _activity_score([], [])
    assert score == 0
    events = [{"created_at": "2026-09-20T00:00:00Z"} for _ in range(50)]
    repos = [{"pushed_at": "2026-09-20T00:00:00Z"} for _ in range(5)]
    score, _ = _activity_score(events, repos)
    assert score == 5


def test_github_enrichment_failure_is_data_not_exception():
    """Private/missing profile -> status, never an exception (offline: no network call)."""
    gh = GitHubEnrichment(username="ghost", status="not_found",
                          summary="GitHub profile not found")
    assert gh.score == 0
    assert gh.status == "not_found"


def test_github_score_capped_at_10():
    gh = GitHubEnrichment(username="x", status="ok", activity_score=5, repo_score=5)
    assert gh.score == 10
