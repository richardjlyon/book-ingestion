"""Sniff the format of an input file.

Routes to a backend by extension first, then verifies the file's magic bytes
match before returning. This catches accidental mis-extensions early.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

Format = Literal["pdf", "epub"]

_PDF_MAGIC = b"%PDF"
_ZIP_MAGIC = b"PK\x03\x04"  # EPUB is a zip
_SNIFF_BYTES = 8


def detect_format(path: Path) -> Format:
    """Return the format tag of `path`.

    Raises ValueError when the file does not match a supported format or when
    the extension and the magic bytes disagree.
    """
    suffix = path.suffix.lower()
    with path.open("rb") as f:
        head = f.read(_SNIFF_BYTES)

    if suffix == ".pdf":
        if not head.startswith(_PDF_MAGIC):
            raise ValueError(
                f"{path} has .pdf extension but is not a valid PDF (magic mismatch)"
            )
        return "pdf"
    if suffix == ".epub":
        if not head.startswith(_ZIP_MAGIC):
            raise ValueError(
                f"{path} has .epub extension but is not a valid EPUB (zip magic mismatch)"
            )
        return "epub"

    raise ValueError(f"unsupported format: {path.name} (suffix: {suffix or 'none'})")
