"""PDF metadata extractor — pypdf-based.

Implements `MetadataExtractor` for PDFs. Reads `/Info` and the first N
pages of text. No Docling on this path.

See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §5.
"""
from __future__ import annotations

import logging
from pathlib import Path

from book_ingestion.metadata import (
    BookMetadata,
    ErrorCode,
    MetadataWarning,
    WarningCode,
)

logger = logging.getLogger(__name__)


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

        # Subsequent tasks populate identifier, title, creators, etc.
        return BookMetadata()
