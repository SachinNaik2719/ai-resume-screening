"""Human-readable PDF report of a screening run (for quick review).

The machine-readable contract stays results.json; this PDF is a reading aid:
batch summary, ranked candidates with score bars + evidence, rejected list.
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from .config import SCORE_MAX
from .models import ResultsFile

_PAGE_W = 190  # usable width with 10mm margins on A4


def _safe(text: str) -> str:
    """Core-font-safe text: map common unicode punctuation, drop the rest."""
    replacements = {
        "—": "-", "–": "-", "‘": "'", "’": "'",
        "“": '"', "”": '"', "•": "-", "…": "...",
        "→": "->", "×": "x", "≥": ">=", "≤": "<=",
        "·": "-", "‐": "-", "‑": "-",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text.encode("latin-1", "replace").decode("latin-1")


class ReportPDF(FPDF):
    def footer(self) -> None:  # noqa: D102
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"page {self.page_no()}/{{nb}}", align="R")
        self.set_text_color(0, 0, 0)


def _section_title(pdf: ReportPDF, title: str) -> None:
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(20, 60, 120)
    pdf.ln(4)
    pdf.multi_cell(w=0, h=8, text=_safe(title),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(20, 60, 120)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + _PAGE_W, pdf.get_y())
    pdf.ln(2)
    pdf.set_text_color(0, 0, 0)


def _kv_table(pdf: ReportPDF, rows: list[tuple[str, str]]) -> None:
    pdf.set_font("Helvetica", "", 10)
    for index, (key, value) in enumerate(rows):
        fill = index % 2 == 0
        if fill:
            pdf.set_fill_color(238, 242, 248)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(70, 7, _safe(key), border=1, fill=fill)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(120, 7, _safe(value), border=1, fill=fill,
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _score_bar(pdf: ReportPDF, label: str, value: int, cap: int,
               color: tuple[int, int, int]) -> None:
    """Horizontal bar: label | bar | n/cap."""
    bar_w = 70
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(38, 6, _safe(label), new_x=XPos.RIGHT, new_y=YPos.TOP)
    ratio = 0 if cap == 0 else max(0.0, min(1.0, value / cap))
    pdf.set_draw_color(170, 170, 170)
    pdf.rect(pdf.get_x(), pdf.get_y() + 1, bar_w, 4)
    if ratio > 0:
        pdf.set_fill_color(*color)
        pdf.rect(pdf.get_x(), pdf.get_y() + 1, bar_w * ratio, 4, style="F")
    pdf.set_x(pdf.get_x() + bar_w + 4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(20, 6, f"{value}/{cap}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _candidate_block(pdf: ReportPDF, result, evidence_lines: int = 3) -> None:
    # Estimate height to avoid splitting a candidate across pages (~4 lines min).
    pdf.accept_block() if hasattr(pdf, "accept_block") else None
    pdf.set_fill_color(245, 247, 250)

    # Header line: rank + name + total
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(20, 60, 120)
    head = f"#{result.rank}  {result.candidate_name}  -  {result.total_score} / 100"
    pdf.multi_cell(w=0, h=6, text=_safe(head),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(w=0, h=4.5,
                   text=_safe(f"file: {result.filename}  |  method: {result.scoring_method}"
                              + (f"  |  github: {result.github_enrichment_status}"
                                 if result.github_enrichment_status else "")),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    b = result.score_breakdown
    _score_bar(pdf, "AI/agentic depth", b.ai_project_depth,
               SCORE_MAX["ai_project_depth"], (36, 130, 90))
    _score_bar(pdf, "Python/backend", b.python_backend,
               SCORE_MAX["python_backend"], (30, 90, 180))
    _score_bar(pdf, "Cloud/full-stack", b.cloud_fullstack,
               SCORE_MAX["cloud_fullstack"], (160, 110, 30))
    _score_bar(pdf, "GitHub activity", b.github, SCORE_MAX["github"], (110, 70, 160))
    _score_bar(pdf, "Eng. depth", b.engineering_depth,
               SCORE_MAX["engineering_depth"], (60, 60, 60))
    if b.penalty:
        _score_bar(pdf, "Penalty", b.penalty, 0, (180, 40, 40))
        pdf.set_xy(pdf.l_margin + 38, pdf.get_y() - 6)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(180, 40, 40)
        pdf.cell(94, 6, f"penalty {b.penalty}",
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    if result.matched_skills:
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(w=0, h=4.5,
                       text=_safe("skills: " + ", ".join(result.matched_skills[:14])),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if result.project_summary:
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(w=0, h=4.5, text=_safe("top project: " + result.project_summary),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # Evidence (why this score) — a few lines only, full trail stays in JSON.
    flat: list[str] = []
    for category in ("ai_project_depth", "python_backend", "cloud_fullstack"):
        flat.extend(result.evidence.get(category, [])[:2])
    if flat:
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(70, 70, 70)
        for line in flat[:evidence_lines]:
            pdf.multi_cell(w=0, h=4.2, text=_safe("  evidence: " + line),
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    if result.github_summary:
        pdf.set_font("Helvetica", "", 8)
        pdf.multi_cell(w=0, h=4.2, text=_safe("github: " + result.github_summary),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    strengths = ", ".join(result.strengths[:3])
    concerns = ", ".join(result.concerns[:3])
    pdf.set_font("Helvetica", "", 9)
    if strengths:
        pdf.set_text_color(36, 130, 90)
        pdf.multi_cell(w=0, h=4.5, text=_safe("+ " + strengths),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if concerns:
        pdf.set_text_color(180, 110, 30)
        pdf.multi_cell(w=0, h=4.5, text=_safe("! " + concerns),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)


def write_pdf_report(results: ResultsFile, path: str | Path) -> Path:
    """Render a human-reviewable PDF; returns the written path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    pdf = ReportPDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()

    # Title block
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(20, 60, 120)
    pdf.multi_cell(w=0, h=9, text="AI Resume Screening Report",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(w=0, h=5,
                   text=_safe(f"generated: {results.generated_at[:19]}   "
                              f"input: {results.input_dir}"),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # Batch summary
    _section_title(pdf, "Batch Summary")
    s = results.batch_summary
    _kv_table(pdf, [
        ("total files", str(s.total_files)),
        ("parsed OK", str(s.parsed_ok)),
        ("parse failures", str(s.parse_failures)),
        ("duplicates skipped", str(s.duplicates_skipped)),
        ("unsupported files", str(s.unsupported_files)),
        ("eligible", str(s.eligible)),
        ("rejected", str(s.rejected)),
        ("scoring method", s.scoring_method),
        ("LLM calls ok / failed", f"{s.llm_calls_ok} / {s.llm_calls_failed}"),
        ("GitHub enriched / failures", f"{s.github_enriched} / {s.github_failures}"),
    ])

    # Rubric reminder
    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(w=0, h=4.5,
                   text=_safe("Rubric: AI depth 40 | Python/backend 30 | "
                              "Cloud/full-stack 15 | GitHub 10 | Eng. depth 5 | "
                              "penalties -5..-15"),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(0, 0, 0)

    # Ranked candidates
    if results.results:
        _section_title(pdf, f"Ranked Candidates ({len(results.results)})")
        for result in results.results:
            _candidate_block(pdf, result)

    # Rejected
    if results.rejected:
        pdf.add_page()
        _section_title(pdf, f"Rejected Candidates ({len(results.rejected)})")
        pdf.set_font("Helvetica", "", 10)
        for verdict in results.rejected:
            reason = "; ".join(verdict.rejection_reasons)
            skills = ", ".join(verdict.matched_skills[:8])
            line = f"- {verdict.candidate} ({verdict.filename}): {reason}"
            if skills:
                line += f"  [matched: {skills}]"
            pdf.multi_cell(w=0, h=5, text=_safe(line),
                           new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # How to read this
    pdf.ln(6)
    _section_title(pdf, "How to Read This Report")
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(
        w=0, h=5,
        text=_safe(
            "Scores blend a deterministic rule baseline with LLM judgment "
            "(hybrid), always inside the rubric caps; the stricter of the two "
            "penalties wins. Every point in results.json carries an evidence "
            "array quoting the resume section that earned it. Rejections are "
            "pure rules: Python evidence AND a meaningful AI/agentic project "
            "are both required. GitHub adds up to 10 bonus points and never "
            "blocks a candidate when missing, private, or rate-limited."
        ),
        new_x=XPos.LMARGIN, new_y=YPos.NEXT,
    )

    pdf.output(str(out))
    return out
