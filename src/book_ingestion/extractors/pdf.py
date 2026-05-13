"""PDF metadata extractor — pypdf-based.

Implements `MetadataExtractor` for PDFs. Reads `/Info` and the first N
pages of text. No Docling on this path.

See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §5.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

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

        return BookMetadata(
            identifier=identifier,
            warnings=warnings,
        )
