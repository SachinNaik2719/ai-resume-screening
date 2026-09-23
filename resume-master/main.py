#!/usr/bin/env python3
"""CLI entry point.

    python main.py --input ./resumes --output ./output/results.json
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow running without installing the package.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from resume_screener.config import load_settings  # noqa: E402
from resume_screener.pdf_report import write_pdf_report  # noqa: E402
from resume_screener.pipeline import run_pipeline  # noqa: E402
from resume_screener.report import print_summary, write_csv, write_json  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI resume screening: parse -> filter -> score -> rank",
    )
    parser.add_argument("--input", "-i", required=True,
                        help="directory containing resume files (pdf/docx/txt)")
    parser.add_argument("--output", "-o", default="./output/results.json",
                        help="path for results JSON (default ./output/results.json)")
    parser.add_argument("--csv", default=None,
                        help="optional path for a flat CSV summary")
    parser.add_argument("--pdf", default=None,
                        help="optional path for a human-readable PDF report")
    parser.add_argument("--no-llm", action="store_true",
                        help="force rule-based scoring even if an API key is set")
    parser.add_argument("--no-github", action="store_true",
                        help="skip GitHub enrichment entirely")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="debug-level logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    settings = load_settings()
    if args.no_llm:
        settings = settings.without_llm()
    if args.no_github:
        settings = settings.without_github()

    if not settings.llm_available:
        logging.info("LLM not configured/used -> rule-based scoring for this run")
    else:
        logging.info("LLM scoring enabled: %s @ %s",
                     settings.llm_model, settings.llm_base_url)

    try:
        results = run_pipeline(args.input, settings)
    except FileNotFoundError as exc:
        logging.error("%s", exc)
        return 2

    out_path = write_json(results, args.output)
    if args.csv:
        write_csv(results, args.csv)
    if args.pdf:
        pdf_path = write_pdf_report(results, args.pdf)
        print(f"PDF report written to: {pdf_path}")
    print_summary(results)
    print(f"\nResults written to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
