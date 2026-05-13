"""Tests for PdfMetadataExtractor + supporting PDF fixture helpers."""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from book_ingestion.metadata import EditionHint, IdentifierKind
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


def test_pdf_extracts_paperback_isbn(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import WarningCode

    p = build_pdf_with_imprint(
        tmp_path / "p.pdf",
        title="Sample",
        subtitle="A Subtitle",
        isbn_paperback="9781234567897",
        isbn_hardback="9781234567880",
        publisher="Example Press",
        places=["London"],
        year=2003,
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.identifier.kind == IdentifierKind.ISBN
    assert m.identifier.value == "9781234567897"  # paperback wins
    assert len(m.identifier.candidates) == 2
    assert {c.edition_hint for c in m.identifier.candidates} == {
        EditionHint.PAPERBACK, EditionHint.HARDBACK,
    }
    codes = {w.code for w in m.warnings}
    assert WarningCode.MULTIPLE_ISBNS_DETECTED in codes


def test_pdf_dedupes_isbn10_and_isbn13_no_warning(tmp_path: Path) -> None:
    """When a paperback prints both ISBN-10 and ISBN-13 forms, no MULTIPLE warning."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import WarningCode

    p = tmp_path / "dual.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "Title")
    c.showPage()
    c.drawString(72, 720, "Paperback ISBN 1-84467-487-8")
    c.drawString(72, 700, "Paperback ISBN 978-1-84467-487-9")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.identifier.value == "9781844674879"  # ISBN-13 form
    assert len(m.identifier.candidates) == 1
    codes = {w.code for w in m.warnings}
    assert WarningCode.MULTIPLE_ISBNS_DETECTED not in codes


def test_pdf_extracts_doi(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = tmp_path / "doi.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "DOI: 10.1234/abcde.fghij")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.identifier.kind == IdentifierKind.DOI
    assert m.identifier.value == "10.1234/abcde.fghij"


def test_pdf_extracts_arxiv(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = tmp_path / "arxiv.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "arXiv: 2301.12345")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.identifier.kind == IdentifierKind.ARXIV
    assert m.identifier.value == "2301.12345"
