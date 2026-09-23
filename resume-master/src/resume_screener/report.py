"""Output serialization: results.json (+ optional CSV)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import ResultsFile


def write_json(results: ResultsFile, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        results.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return out


def write_csv(results: ResultsFile, path: str | Path) -> Path:
    """Flat CSV view of eligible candidates (convenience alongside JSON)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank", "candidate_name", "filename", "total_score",
        "ai_project_depth", "python_backend", "cloud_fullstack",
        "github", "engineering_depth", "penalty",
        "github_enrichment_status", "scoring_method",
    ]
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results.results:
            b = result.score_breakdown
            writer.writerow({
                "rank": result.rank,
                "candidate_name": result.candidate_name,
                "filename": result.filename,
                "total_score": result.total_score,
                "ai_project_depth": b.ai_project_depth,
                "python_backend": b.python_backend,
                "cloud_fullstack": b.cloud_fullstack,
                "github": b.github,
                "engineering_depth": b.engineering_depth,
                "penalty": b.penalty,
                "github_enrichment_status": result.github_enrichment_status,
                "scoring_method": result.scoring_method,
            })
    return out


def print_summary(results: ResultsFile) -> None:
    """Compact terminal report of the run."""
    summary = results.batch_summary
    print("\n=== Batch Summary ===")
    print(f"  files: {summary.total_files}  parsed: {summary.parsed_ok}  "
          f"failures: {summary.parse_failures}  duplicates: {summary.duplicates_skipped}")
    print(f"  eligible: {summary.eligible}  rejected: {summary.rejected}  "
          f"unsupported: {summary.unsupported_files}")
    print(f"  scoring: {summary.scoring_method}  "
          f"(llm ok/failed: {summary.llm_calls_ok}/{summary.llm_calls_failed})")
    print(f"  github: enriched {summary.github_enriched}, "
          f"failures {summary.github_failures}")

    if results.results:
        print("\n=== Top Candidates ===")
        header = f"{'#':>2}  {'score':>5}  {'AI':>3} {'Py':>3} {'Cloud':>5} {'GH':>3} {'Eng':>3} {'pen':>4}  name"
        print(header)
        for result in results.results[:10]:
            b = result.score_breakdown
            print(f"{result.rank:>2}  {result.total_score:>5}  "
                  f"{b.ai_project_depth:>3} {b.python_backend:>3} "
                  f"{b.cloud_fullstack:>5} {b.github:>3} {b.engineering_depth:>3} "
                  f"{b.penalty:>4}  {result.candidate_name}")

    if results.rejected:
        print("\n=== Rejected ===")
        for verdict in results.rejected:
            print(f"  - {verdict.candidate}: {'; '.join(verdict.rejection_reasons)}")
