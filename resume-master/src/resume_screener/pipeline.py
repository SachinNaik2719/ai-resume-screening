"""Batch orchestration: ingest -> eligibility -> scoring -> enrichment -> rank.

Reliability contract: a single malformed resume, a failed LLM call, or a
GitHub rate limit only annotates that candidate — the run always completes.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .config import SUPPORTED_EXTENSIONS, Settings
from .eligibility import check_eligibility
from .extraction import extract_candidate_info
from .models import (
    BatchSummary,
    CandidateResult,
    EligibilityResult,
    ExtractedInfo,
    ResultsFile,
)
from .parsing import parse_file
from .scoring.github import enrich_batch
from .scoring.llm_client import LLMClient
from .scoring.llm_scorer import score_with_llm
from .scoring.rules import rule_score

logger = logging.getLogger("resume_screener")


def _list_resume_files(input_dir: Path) -> tuple[list[Path], int]:
    """Flat directory listing; returns (supported files, unsupported count)."""
    supported: list[Path] = []
    unsupported = 0
    for path in sorted(input_dir.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_dir():
            continue
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            supported.append(path)
        else:
            unsupported += 1
            logger.warning("skipping unsupported file: %s", path.name)
    return supported, unsupported


def run_pipeline(input_dir: str | Path, settings: Settings) -> ResultsFile:
    """Execute the full screening run and return the structured result."""
    input_path = Path(input_dir)
    if not input_path.is_dir():
        raise FileNotFoundError(f"input directory not found: {input_path}")

    files, unsupported = _list_resume_files(input_path)
    summary = BatchSummary(total_files=len(files) + unsupported,
                           unsupported_files=unsupported)
    scoring_method = "hybrid_llm" if settings.llm_available else "rule_based"
    summary.scoring_method = scoring_method

    # ---------------------------------------------------------------- parse --
    parsed, duplicates_seen = [], set()
    for file in files:
        resume = parse_file(file)
        if resume.parsed_ok:
            if resume.sha256 and resume.sha256 in duplicates_seen:
                summary.duplicates_skipped += 1
                logger.info("duplicate file skipped: %s", file.name)
                continue
            if resume.sha256:
                duplicates_seen.add(resume.sha256)
            summary.parsed_ok += 1
        else:
            summary.parse_failures += 1
            logger.warning("parse failure: %s (%s)", file.name, resume.parse_error)
        parsed.append(resume)

    # ---------------------------------------------------- extract + filter --
    eligible: list[tuple[object, ExtractedInfo, EligibilityResult]] = []
    rejected: list[EligibilityResult] = []
    for resume in parsed:
        if not resume.parsed_ok:
            rejected.append(EligibilityResult(
                candidate=resume.filename,
                filename=resume.filename,
                eligible=False,
                rejection_reasons=[f"Unreadable resume: {resume.parse_error}"],
            ))
            continue
        info = extract_candidate_info(resume.text)
        verdict = check_eligibility(info, filename=resume.filename)
        if verdict.eligible:
            eligible.append((resume, info, verdict))
        else:
            rejected.append(verdict)

    summary.eligible = len(eligible)
    summary.rejected = len(rejected)

    # ----------------------------------------------------- github enrich ----
    urls = {
        resume.filename: info.github_url
        for resume, info, _ in eligible
    }
    github_results = enrich_batch(urls, settings) if urls else {}
    summary.github_enriched = sum(
        1 for g in github_results.values() if g.status == "ok"
    )
    summary.github_failures = sum(
        1 for g in github_results.values()
        if g.status in {"rate_limited", "error", "not_found"}
    )

    # -------------------------------------------------------------- score ---
    client = LLMClient(settings)

    def _score_one(item):
        resume, info, verdict = item
        errors: list[str] = []
        rule = rule_score(info)
        gh = github_results.get(resume.filename)
        if gh is not None:
            rule.breakdown.github = gh.score  # cap built into GitHubEnrichment.score
            if gh.status != "ok" and gh.status != "disabled":
                errors.append(f"github: {gh.summary or gh.status}")

        if settings.llm_available:
            breakdown, evidence, method, _llm_value, llm_error = score_with_llm(
                info, verdict, rule, client, settings
            )
            breakdown.github = rule.breakdown.github
            if llm_error:
                errors.append(f"llm: {llm_error}")
                method = "rule_based" if _llm_value is None else method
        else:
            breakdown, evidence, method = rule.breakdown, rule.evidence, "rule_based"

        return resume, info, verdict, breakdown, evidence, method, errors, gh

    scored = []
    if eligible:
        with ThreadPoolExecutor(max_workers=settings.max_workers) as pool:
            scored = list(pool.map(_score_one, eligible))

    # ------------------------------------------------------------- assemble -
    results: list[CandidateResult] = []
    llm_ok = 0
    llm_failed = 0
    for resume, info, verdict, breakdown, evidence, method, errors, gh in scored:
        if settings.llm_available:
            if any(e.startswith("llm:") for e in errors):
                llm_failed += 1
            else:
                llm_ok += 1
        results.append(CandidateResult(
            candidate_name=verdict.candidate,
            filename=resume.filename,
            eligible=True,
            total_score=breakdown.total(),
            score_breakdown=breakdown,
            matched_skills=verdict.matched_skills,
            project_summary=info.summary,
            github_url=info.github_url,
            github_summary=gh.summary if gh else None,
            github_enrichment_status=gh.status if gh else None,
            strengths=_default_strengths(breakdown),
            concerns=_default_concerns(breakdown, errors),
            evidence=evidence,
            scoring_method=method,
            errors=errors,
        ))

    results.sort(key=lambda r: r.total_score, reverse=True)
    for index, result in enumerate(results, start=1):
        result.rank = index

    summary.llm_calls_ok = llm_ok
    summary.llm_calls_failed = llm_failed

    return ResultsFile(
        generated_at=datetime.now(timezone.utc).isoformat(),
        input_dir=str(input_path),
        batch_summary=summary,
        results=results,
        rejected=rejected,
    )


def _default_strengths(breakdown) -> list[str]:
    strengths = []
    if breakdown.ai_project_depth >= 28:
        strengths.append("Strong AI/agentic project depth")
    elif breakdown.ai_project_depth >= 18:
        strengths.append("Solid AI project exposure")
    if breakdown.python_backend >= 20:
        strengths.append("Strong Python/backend engineering")
    if breakdown.cloud_fullstack >= 8:
        strengths.append("Deployment/full-stack exposure")
    if breakdown.github >= 6:
        strengths.append("Active public GitHub presence")
    if breakdown.engineering_depth >= 3:
        strengths.append("Engineering-depth signals (testing/ops/architecture)")
    return strengths or ["Meets minimum Python + AI bar"]


def _default_concerns(breakdown, errors: list[str]) -> list[str]:
    concerns = []
    if breakdown.penalty < 0:
        concerns.append(f"Project-quality penalty applied ({breakdown.penalty})")
    if breakdown.ai_project_depth < 20:
        concerns.append("Limited depth in AI/agentic implementation details")
    if breakdown.github < 3:
        concerns.append("Little or no public GitHub signal")
    if breakdown.cloud_fullstack < 5:
        concerns.append("Limited cloud/deployment evidence")
    concerns.extend(errors)
    return concerns
