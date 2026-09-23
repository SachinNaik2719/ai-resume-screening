"""PDF text extraction via pypdf."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"encrypted PDF, cannot read: {exc}") from exc
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)
