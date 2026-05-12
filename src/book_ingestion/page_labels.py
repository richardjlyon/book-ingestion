"""Printed page labels for PDFs.

Two paths:
  1. `read_pdf_page_labels()` — exact, reads the PDF /PageLabels dictionary.
  2. `infer_page_labels_from_blocks()` — heuristic, scans running headers/footers.

Both return a dict[int, str] mapping PDF page index (1-based) to printed label,
or None if no mapping could be produced.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_pdf_page_labels(path: Path) -> dict[int, str] | None:
    """Read the PDF /PageLabels dictionary via pypdf.

    Returns a dict mapping PDF page index (1-based, matching Docling's `page_no`)
    to the printed page label. Returns None if the PDF has no /PageLabels entry
    or if pypdf cannot parse the file.
    """
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        logger.warning("pypdf not installed; cannot read /PageLabels")
        return None

    try:
        reader = PdfReader(str(path))
    except (PdfReadError, OSError, ValueError) as exc:
        logger.warning("pypdf failed to read %s: %s", path, exc)
        return None

    # pypdf exposes `page_labels` as a list aligned to pages (0-indexed).
    # When /PageLabels is absent, pypdf falls back to "1","2",... which is
    # indistinguishable from genuine numeric labels — so we explicitly check
    # the /PageLabels entry in the catalog.
    root = reader.trailer.get("/Root") if reader.trailer else None
    catalog = root.get_object() if root is not None else None
    if catalog is None or "/PageLabels" not in catalog:
        return None

    labels: dict[int, str] = {}
    for i, _page in enumerate(reader.pages, start=1):
        try:
            label = reader.page_labels[i - 1]
        except (IndexError, KeyError, AttributeError):
            continue
        if label:
            labels[i] = str(label)
    return labels or None
