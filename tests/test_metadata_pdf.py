"""Tests for PdfMetadataExtractor + supporting PDF fixture helpers."""
from __future__ import annotations

from pathlib import Path

from tests.fixtures.pdf import (
    build_encrypted_pdf,
    build_pdf_with_all_caps_title,
    build_pdf_with_imprint,
    build_scanned_pdf,
)


def test_pdf_fixture_imprint_builds(tmp_path: Path) -> None:
    p = build_pdf_with_imprint(
        tmp_path / "imprint.pdf",
        title="Sample Book",
        subtitle="An Example",
        isbn_paperback="9781234567897",
        isbn_hardback="9781234567880",
        publisher="Example Press",
        places=["London", "New York"],
        year=2003,
        first_published_year=2000,
    )
    assert p.exists() and p.stat().st_size > 1000


def test_pdf_fixture_all_caps_builds(tmp_path: Path) -> None:
    p = build_pdf_with_all_caps_title(
        tmp_path / "caps.pdf",
        title_lines=["THE HOLOCAUST INDUSTRY"],
        subtitle="REFLECTIONS ON THE EXPLOITATION",
        author="Norman G. Finkelstein",
    )
    assert p.exists() and p.stat().st_size > 1000


def test_pdf_fixture_encrypted_builds(tmp_path: Path) -> None:
    p = build_encrypted_pdf(tmp_path / "enc.pdf", password="secret")
    assert p.exists() and p.stat().st_size > 0


def test_pdf_fixture_scanned_builds(tmp_path: Path) -> None:
    p = build_scanned_pdf(tmp_path / "scanned.pdf")
    assert p.exists() and p.stat().st_size > 0


def test_pdf_encrypted_returns_error(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import BookMetadata, ErrorCode

    p = build_encrypted_pdf(tmp_path / "enc.pdf", password="secret")
    m = PdfMetadataExtractor().extract_metadata(p)
    assert isinstance(m, BookMetadata)
    assert m.error == ErrorCode.ENCRYPTED
    assert m.title is None
    assert m.creators == []


def test_pdf_scanned_returns_no_text_warning(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import WarningCode

    p = build_scanned_pdf(tmp_path / "scanned.pdf")
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.error is None
    codes = {w.code for w in m.warnings}
    assert WarningCode.NO_TEXT_EXTRACTED in codes
