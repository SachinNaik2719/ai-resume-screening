"""Pipeline tests: batch resilience, duplicates, JSON output shape."""
from __future__ import annotations

import json
from pathlib import Path

from resume_screener.pipeline import run_pipeline
from resume_screener.report import write_csv, write_json

STRONG = """Asha Rao
asha@email.com
github.com/coderao

SKILLS
Python, FastAPI, LangGraph, RAG, Docker, GCP, pytest

PROJECTS
- RAG Agent
- Multi-agent workflow with LangGraph: retrieval, embeddings, tool calling, evaluation pipeline.
- FastAPI async backend with Redis caching, deployed on GCP Cloud Run.
"""

NO_AI = """Ben Kim
ben@email.com

SKILLS
Python, Django, PostgreSQL

PROJECTS
- Blog API with Django REST and Redis caching.
"""

NO_PYTHON = """Cara Diaz
cara@email.com

SKILLS
Java, React, Spring Boot

PROJECTS
- Shop backend in Spring Boot with React UI.
"""


def _write_set(folder: Path) -> None:
    (folder / "a_strong.txt").write_text(STRONG, encoding="utf-8")
    (folder / "b_no_ai.txt").write_text(NO_AI, encoding="utf-8")
    (folder / "c_no_python.txt").write_text(NO_PYTHON, encoding="utf-8")
    # corrupt pdf + empty file + duplicate + unsupported
    (folder / "d_corrupt.pdf").write_bytes(b"%PDF-1.4 not really a pdf")
    (folder / "e_empty.txt").write_text("   ", encoding="utf-8")
    (folder / "f_duplicate.txt").write_text(STRONG, encoding="utf-8")
    (folder / "g_notes.md").write_text("not a resume", encoding="utf-8")


def test_pipeline_survives_bad_files(tmp_path, offline_settings):
    _write_set(tmp_path)
    results = run_pipeline(tmp_path, offline_settings)

    summary = results.batch_summary
    assert summary.parse_failures >= 1  # empty or corrupt counted as failure
    assert summary.duplicates_skipped == 1
    assert summary.unsupported_files == 1  # .md skipped
    # eligible = strong only (duplicate of strong was skipped)
    assert summary.eligible == 1
    assert summary.rejected >= 3
    assert summary.scoring_method == "rule_based"

    top = results.results[0]
    assert top.rank == 1
    assert top.eligible is True
    assert top.total_score > 0
    assert top.score_breakdown.ai_project_depth > 0


def test_rejected_have_reasons(tmp_path, offline_settings):
    _write_set(tmp_path)
    results = run_pipeline(tmp_path, offline_settings)
    reasons = {v.filename: v.rejection_reasons for v in results.rejected}
    assert any("No AI" in r for rs in reasons.values() for r in rs)
    assert any("No evidence of Python" in r for rs in reasons.values() for r in rs)
    assert any("Unreadable resume" in r for rs in reasons.values() for r in rs)


def test_output_json_and_csv(tmp_path, offline_settings):
    _write_set(tmp_path)
    results = run_pipeline(tmp_path, offline_settings)

    json_path = write_json(results, tmp_path / "out" / "results.json")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "batch_summary" in data
    assert data["results"], "eligible candidates must be present"
    required = {"rank", "candidate_name", "eligible", "total_score",
                "score_breakdown", "matched_skills", "project_summary"}
    assert required.issubset(data["results"][0].keys())
    breakdown_keys = {"ai_project_depth", "python_backend", "cloud_fullstack",
                      "github", "engineering_depth"}
    assert breakdown_keys.issubset(data["results"][0]["score_breakdown"].keys())

    csv_path = write_csv(results, tmp_path / "out" / "results.csv")
    assert csv_path.exists()
    assert "total_score" in csv_path.read_text(encoding="utf-8").splitlines()[0]


def test_ranks_are_descending(tmp_path, offline_settings):
    _write_set(tmp_path)
    results = run_pipeline(tmp_path, offline_settings)
    scores = [r.total_score for r in results.results]
    assert scores == sorted(scores, reverse=True)
    assert [r.rank for r in results.results] == list(range(1, len(scores) + 1))


def test_missing_input_dir_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        run_pipeline(tmp_path / "does_not_exist", None)  # type: ignore[arg-type]
