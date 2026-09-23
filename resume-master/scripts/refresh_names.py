"""Re-extract candidate names into an existing results.json.

Keeps scores (including surviving LLM hybrid judgments) intact — useful when
name-extraction logic improves after a run. Rewrites JSON, CSV and PDF.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from resume_screener.eligibility import _fallback_label
from resume_screener.extraction import extract_candidate_info
from resume_screener.models import ResultsFile
from resume_screener.parsing import parse_file
from resume_screener.pdf_report import write_pdf_report
from resume_screener.report import write_csv, write_json

RESULTS = Path("output/results.json")


def better(new: str, old: str) -> bool:
    """Prefer a real extracted name over a placeholder or a mangled line."""
    if not new:
        return False
    if not old:
        return True
    if "@" in old or old.lower().endswith("."):
        return True
    return False


def main() -> None:
    data = ResultsFile.model_validate_json(RESULTS.read_text(encoding="utf-8"))
    base = Path(data.input_dir)
    updated = 0

    for entry in list(data.results) + list(data.rejected):
        path = base / entry.filename
        if not path.exists():
            continue
        parsed = parse_file(path)
        if not parsed.parsed_ok:
            continue
        info = extract_candidate_info(parsed.text)
        old_name = getattr(entry, "candidate_name", None) or getattr(entry, "candidate", "") or ""
        new_name = info.name or _fallback_label(entry.filename)
        if better(info.name, old_name):
            if hasattr(entry, "candidate_name"):
                entry.candidate_name = new_name
            if hasattr(entry, "candidate"):
                entry.candidate = new_name
            updated += 1
        # Also refresh github url-derived fields if extractor improved
        if hasattr(entry, "github_url") and info.github_url and not entry.github_url:
            entry.github_url = info.github_url

    write_json(data, RESULTS)
    write_csv(data, "output/results.csv")
    write_pdf_report(data, "output/report.pdf")
    print(f"updated names: {updated}")
    print("rewrote output/results.json, output/results.csv, output/report.pdf")


if __name__ == "__main__":
    main()
