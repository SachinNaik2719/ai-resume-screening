"""File parsers: dispatch by extension, never raise into the pipeline."""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..models import ParsedResume
from .docx import read_docx
from .pdf import read_pdf
from .txt import read_txt

_READERS = {
    ".pdf": read_pdf,
    ".docx": read_docx,
    ".txt": read_txt,
    ".text": read_txt,
}


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def parse_file(path: Path) -> ParsedResume:
    """Parse one resume file. All failures are captured in ``parse_error``."""
    suffix = path.suffix.lower()
    reader = _READERS.get(suffix)
    parsed = ParsedResume(
        path=str(path),
        filename=path.name,
        format=suffix.lstrip(".") or "unknown",
        sha256=_sha256(path),
    )
    if reader is None:
        parsed.parse_error = f"unsupported file extension '{suffix or '(none)'}'"
        parsed.format = "unknown"
        return parsed
    if not path.is_file():
        parsed.parse_error = "not a readable file"
        return parsed
    try:
        parsed.text = reader(path)
    except Exception as exc:  # noqa: BLE001 — one bad file must not kill the batch
        parsed.parse_error = f"{type(exc).__name__}: {exc}"
        return parsed
    if not parsed.text.strip():
        parsed.parse_error = "no extractable text (empty or scanned image PDF?)"
    return parsed
