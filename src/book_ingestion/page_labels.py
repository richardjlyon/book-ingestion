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

    Returns a dict[int, str] when ≥ _MIN_RUN consecutive pages show a monotone
    integer progression in any candidate slot. Returns None otherwise.
    """
    if not page_texts:
        return None

    candidates: dict[int, list[tuple[str, int]]] = {}
    for page, texts in page_texts.items():
        page_candidates = [c for t in texts if (c := _candidate_label(t)) is not None]
        if page_candidates:
            candidates[page] = page_candidates

    sorted_pages = sorted(candidates.keys())
    if len(sorted_pages) < _MIN_RUN:
        return None

    def _first(cs: list[tuple[str, int]]) -> tuple[str, int]:
        return cs[0]

    def _last(cs: list[tuple[str, int]]) -> tuple[str, int]:
        return cs[-1]

    best: dict[int, str] = {}
    for slot_picker in (_first, _last):
        chosen: dict[int, tuple[str, int]] = {
            p: slot_picker(candidates[p]) for p in sorted_pages
        }
        run: list[int] = []
        for p in sorted_pages:
            _label, val = chosen[p]
            if run and (p == run[-1] + 1) and (chosen[run[-1]][1] + 1 == val):
                run.append(p)
            else:
                run = [p]
            if len(run) >= _MIN_RUN and len(run) > len(best):
                best = {pp: chosen[pp][0] for pp in run}
        if best:
            break

    return best or None
