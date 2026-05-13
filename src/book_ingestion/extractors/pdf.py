"""PDF metadata extractor — pypdf-based.

Implements `MetadataExtractor` for PDFs. Reads `/Info` and the first N
pages of text. No Docling on this path.

See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §5.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from book_ingestion.metadata import (
    BookMetadata,
    ErrorCode,
    Identifier,
    IdentifierCandidate,
    IdentifierKind,
    MetadataWarning,
    WarningCode,
    canonicalize_isbn,
    classify_edition_hint,
    dedupe_isbn_candidates,
    pick_identifier_value,
)

if TYPE_CHECKING:
    from pypdf import PdfReader

logger = logging.getLogger(__name__)

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"(?:arXiv:\s*|arxiv\.org/abs/)(\d{4}\.\d{4,5})", re.IGNORECASE)
_ISBN13_RE = re.compile(r"(?:ISBN[ -]*)?(97[89][- 0-9]{10,})", re.IGNORECASE)
_ISBN10_RE = re.compile(r"(?:ISBN[ -]*)?([0-9][- 0-9]{8,10}[0-9X])", re.IGNORECASE)


def _extract_identifier(text: str, warnings: list[MetadataWarning]) -> Identifier:
    """Extract identifier from text: DOI, arXiv, or ISBN."""
    # DOI — first match
    doi_m = _DOI_RE.search(text)
    if doi_m:
        value = doi_m.group(0)
        return Identifier(
            kind=IdentifierKind.DOI,
            value=value,
            candidates=[IdentifierCandidate(kind=IdentifierKind.DOI, value=value)],
        )

    # arXiv — first match
    arxiv_m = _ARXIV_RE.search(text)
    if arxiv_m:
        value = arxiv_m.group(1)
        return Identifier(
            kind=IdentifierKind.ARXIV,
            value=value,
            candidates=[IdentifierCandidate(kind=IdentifierKind.ARXIV, value=value)],
        )

    # ISBNs — gather all matches, classify by window, then dedupe.
    raw_candidates: list[IdentifierCandidate] = []
    for m in _ISBN13_RE.finditer(text):
        raw = m.group(1)
        canon = canonicalize_isbn(raw)
        if len(canon) != 13 or not canon.startswith(("978", "979")):
            continue
        window = text[max(0, m.start() - 20) : m.end() + 20]
        raw_candidates.append(IdentifierCandidate(
            kind=IdentifierKind.ISBN, value=canon,
            edition_hint=classify_edition_hint(window),
        ))
    for m in _ISBN10_RE.finditer(text):
        raw = m.group(1)
        canon = canonicalize_isbn(raw)
        if len(canon) != 10:
            continue
        # Note: no need to filter ISBN-10s that look like a substring of an
        # earlier ISBN-13 match. The length-10 filter above plus
        # `dedupe_isbn_candidates` already handle the collision case correctly:
        # for a same-book pair, the ISBN-13's last 10 digits ≠ the ISBN-10
        # (different check digit), and dedupe collapses by ISBN-13 form.
        window = text[max(0, m.start() - 20) : m.end() + 20]
        raw_candidates.append(IdentifierCandidate(
            kind=IdentifierKind.ISBN, value=canon,
            edition_hint=classify_edition_hint(window),
        ))

    if not raw_candidates:
        return Identifier()

    deduped = dedupe_isbn_candidates(raw_candidates)
    if len(deduped) > 1:
        warnings.append(MetadataWarning(
            code=WarningCode.MULTIPLE_ISBNS_DETECTED,
            detail=f"{len(deduped)} distinct ISBN editions detected",
        ))

    isbn_value = pick_identifier_value(deduped)
    return Identifier(
        kind=IdentifierKind.ISBN if isbn_value else None,
        value=isbn_value,
        candidates=deduped,
    )


def _info_title(reader: PdfReader, path: Path) -> str | None:
    """Return /Info /Title if present, non-empty, and not equal to path.stem."""
    info = reader.metadata
    if info is None:
        return None
    raw = info.get("/Title")
    if not raw:
        return None
    text = str(raw).strip()
    if not text or text == path.stem or text.lower() == "untitled":
        return None
    return text


def _is_all_caps(line: str) -> bool:
    has_letter = any(c.isalpha() for c in line)
    return has_letter and line.upper() == line


def _mine_title_from_page_one(text_page_one: str) -> tuple[str | None, str | None]:
    """Return (title, subtitle) from page-1 text mining.

    Strategy (spec §5.3):
      - Find first ALL-CAPS block (consecutive ALL-CAPS lines without trailing punct).
        Join with single spaces. Subtitle = next ALL-CAPS block before author signal.
      - Else, first non-trivial line (≥5 chars, not a page number).
        Subtitle = next non-empty line if shorter than title.
    """
    lines = [line.strip() for line in text_page_one.splitlines() if line.strip()]
    if not lines:
        return None, None

    # ALL-CAPS path: collect consecutive ALL-CAPS lines without trailing punct.
    # Each run of consecutive ALL-CAPS lines forms a block; blocks are separated by
    # non-ALL-CAPS lines, author signal, or when a line looks like a standalone subtitle
    # (relatively long, all-caps line following another relatively long all-caps line).
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.lower().startswith("by "):
            break
        if _is_all_caps(line):
            # Check if this looks like a standalone subtitle:
            # if current block has >= 1 line AND both current[-1] and this line are >= 15 chars
            # and neither has trailing punct, then finalize current and start a new block.
            should_break_before = (
                current
                and len(current[0]) >= 15
                and len(line) >= 15
                and not (current[-1] and current[-1][-1] in ".,:;!?")
                and not (line and line[-1] in ".,:;!?")
            )
            if should_break_before:
                blocks.append(current)
                current = []
            current.append(line)
        else:
            if current:
                blocks.append(current)
                current = []
            # Continue scanning — later ALL-CAPS may be subtitle.
    if current:
        blocks.append(current)

    if blocks:
        title = " ".join(blocks[0])
        subtitle = " ".join(blocks[1]) if len(blocks) > 1 else None
        return title, subtitle

    # First non-trivial line fallback
    for line in lines:
        if len(line) < 5:
            continue
        if line.isdigit():
            continue
        title = line
        # Subtitle: next non-empty line shorter than title
        idx = lines.index(line)
        rest = lines[idx + 1 :]
        for r in rest:
            if r.lower().startswith("by "):
                break
            if 0 < len(r) < len(title):
                return title, r
        return title, None
    return None, None


def _compose_full_title(title: str | None, subtitle: str | None) -> str | None:
    if title is None:
        return None
    if subtitle is None:
        return title
    return f"{title}: {subtitle}"


class PdfMetadataExtractor:
    """PDF metadata extractor.

    `extract_metadata` always returns a BookMetadata; it does not raise on
    file-shape failures. See spec §7.
    """

    name = "pdf_pypdf"

    def extract_metadata(self, path: Path, *, pages: int = 6) -> BookMetadata:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(str(path))
        except (PdfReadError, OSError) as exc:
            logger.warning("pypdf failed to open %s: %s", path, exc)
            return BookMetadata(
                error=ErrorCode.MALFORMED_PDF,
                warnings=[MetadataWarning(
                    code=WarningCode.INCOMPLETE_EXTRACTION, detail=str(exc),
                )],
            )

        if reader.is_encrypted:
            return BookMetadata(error=ErrorCode.ENCRYPTED)

        # Pull text from up to `pages` leading pages.
        page_texts: list[str] = []
        for i, page in enumerate(reader.pages):
            if i >= pages:
                break
            try:
                page_texts.append(page.extract_text() or "")
            except Exception as exc:  # pypdf can raise on malformed streams
                logger.warning("pypdf failed to extract page %d of %s: %s", i, path, exc)
                page_texts.append("")

        joined = "\n".join(page_texts).strip()
        if not joined:
            return BookMetadata(warnings=[
                MetadataWarning(
                    code=WarningCode.NO_TEXT_EXTRACTED,
                    detail="PDF has no embedded text (scanned or empty)",
                ),
            ])

        # Subsequent tasks populate title, creators, etc.
        warnings: list[MetadataWarning] = []
        identifier = _extract_identifier(joined, warnings)

        info_title = _info_title(reader, path)
        if info_title is not None:
            title: str | None = info_title
            subtitle: str | None = None  # /Info has no subtitle field
        else:
            title, subtitle = _mine_title_from_page_one(page_texts[0] if page_texts else "")

        if title is not None and _is_all_caps(title):
            warnings.append(MetadataWarning(code=WarningCode.TITLE_ALL_CAPS_IN_SOURCE))

        full_title = _compose_full_title(title, subtitle)

        return BookMetadata(
            identifier=identifier,
            title=title,
            subtitle=subtitle,
            full_title=full_title,
            warnings=warnings,
        )
