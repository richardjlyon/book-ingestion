"""Printed page labels for PDFs.

Two paths:
  1. `read_pdf_page_labels()` — exact, reads the PDF /PageLabels dictionary.
  2. `infer_page_labels_from_blocks()` — heuristic, scans running headers/footers.

Both return a dict[int, str] mapping PDF page index (1-based) to printed label,
or None if no mapping could be produced.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
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


_ROMAN_LOWER = re.compile(r"^[ivxlcdm]+$")
_ROMAN_UPPER = re.compile(r"^[IVXLCDM]+$")
_ARABIC = re.compile(r"^\d+$")
_MIN_RUN = 4  # need at least 4 consecutive pages of agreement to infer

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman_to_int(s: str) -> int | None:
    """Convert a Roman numeral to int. Returns None on bad input."""
    n = 0
    prev = 0
    for ch in reversed(s.lower()):
        v = _ROMAN_VALUES.get(ch)
        if v is None:
            return None
        n = n - v if v < prev else n + v
        prev = v
    return n if n > 0 else None


def _candidate_label(text: str) -> tuple[str, int] | None:
    """Pick a numeric or roman-numeral label out of a short header/footer line.
    Returns (label, integer_value) or None if no candidate found.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 40:
        return None
    if _ARABIC.match(stripped):
        return (stripped, int(stripped))
    if _ROMAN_LOWER.match(stripped) or _ROMAN_UPPER.match(stripped):
        v = _roman_to_int(stripped)
        if v is not None:
            return (stripped, v)
    tokens = stripped.split()
    for tok in (tokens[0], tokens[-1]):
        if _ARABIC.match(tok):
            return (tok, int(tok))
    return None


def infer_page_labels_from_blocks(
    page_texts: dict[int, list[str]]
) -> dict[int, str] | None:
    """Infer printed page labels from running-header/footer text.

    `page_texts` maps PDF page index → list of short text strings (typically
    the first and last few paragraph-block texts on that page; the caller
    decides what counts as a header/footer candidate).

    Uses a dominant-offset approach: collects (page, value) candidate pairs,
    computes offset = value - page for each, and accepts the most common
    offset if it has ≥ _MIN_RUN supporting pairs. The accepted offset is then
    applied across its observed PDF-page range, filling in gaps (e.g. chapter
    cover pages with no page number). Returns None if no dominant offset
    meets the threshold.
    """
    if not page_texts:
        return None

    # Build (page, value) pairs from the first candidate on each page.
    pairs: list[tuple[int, int]] = []
    for page, texts in sorted(page_texts.items()):
        for t in texts:
            c = _candidate_label(t)
            if c is not None:
                _label, value = c
                pairs.append((page, value))
                break

    if len(pairs) < _MIN_RUN:
        return None

    # Find the dominant offset (value - page).
    offset_counts = Counter(v - p for (p, v) in pairs)
    dominant_offset, support = offset_counts.most_common(1)[0]
    if support < _MIN_RUN:
        return None

    # Determine the observed PDF page range for the dominant offset.
    matching_pages = sorted(p for (p, v) in pairs if v - p == dominant_offset)
    p_min, p_max = matching_pages[0], matching_pages[-1]

    # Apply the offset to every PDF page in that range (fills in gaps).
    labels: dict[int, str] = {}
    for p in range(p_min, p_max + 1):
        value = p + dominant_offset
        if value >= 1:
            labels[p] = str(value)
    return labels or None
