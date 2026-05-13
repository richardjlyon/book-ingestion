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
    build_pdf_with_info_and_all_caps,
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


def test_pdf_uses_info_title_when_present(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = build_pdf_with_imprint(
        tmp_path / "info.pdf",
        title="The Real Title",
        subtitle="Subtitle Here",
        isbn_paperback="9781234567897",
        isbn_hardback="9781234567880",
        publisher="X",
        places=["L"],
        year=2000,
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.title == "The Real Title"


def test_pdf_falls_back_to_all_caps_when_info_blank(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import WarningCode

    p = build_pdf_with_all_caps_title(
        tmp_path / "caps.pdf",
        title_lines=["THE HOLOCAUST INDUSTRY"],
        subtitle="REFLECTIONS ON THE EXPLOITATION",
        author="Norman G. Finkelstein",
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.title == "THE HOLOCAUST INDUSTRY"
    assert m.subtitle == "REFLECTIONS ON THE EXPLOITATION"
    assert m.full_title == "THE HOLOCAUST INDUSTRY: REFLECTIONS ON THE EXPLOITATION"
    codes = {w.code for w in m.warnings}
    assert WarningCode.TITLE_ALL_CAPS_IN_SOURCE in codes


def test_pdf_joins_multi_line_all_caps(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = build_pdf_with_all_caps_title(
        tmp_path / "multi.pdf",
        title_lines=["THE HOLOCAUST", "INDUSTRY"],
        subtitle=None,
        author="Author",
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.title == "THE HOLOCAUST INDUSTRY"
    assert m.subtitle is None
    assert m.full_title == "THE HOLOCAUST INDUSTRY"


def test_pdf_info_title_equal_to_stem_is_ignored(tmp_path: Path) -> None:
    """When /Info /Title is just the filename, fall through to text mining."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = tmp_path / "MyFile.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setTitle("MyFile")  # equal to path.stem
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "REAL TITLE")
    c.save()
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.title == "REAL TITLE"


def test_pdf_extracts_single_author_by_form(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import CreatorRole

    p = tmp_path / "single.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.setFont("Helvetica", 12)
    c.drawString(72, 650, "by Norman G. Finkelstein")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert len(m.creators) == 1
    assert m.creators[0].role == CreatorRole.AUTHOR
    assert m.creators[0].first_name == "Norman G."
    assert m.creators[0].last_name == "Finkelstein"


def test_pdf_extracts_comma_form_author(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = tmp_path / "comma.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.setFont("Helvetica", 12)
    c.drawString(72, 650, "Finkelstein, Norman G.")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert len(m.creators) == 1
    assert m.creators[0].first_name == "Norman G."
    assert m.creators[0].last_name == "Finkelstein"


def test_pdf_preserves_creator_order(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = tmp_path / "two.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.setFont("Helvetica", 12)
    c.drawString(72, 650, "by Jane Smith and John Jones")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert [c.last_name for c in m.creators] == ["Smith", "Jones"]


def test_pdf_detects_translator_role(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import CreatorRole

    p = tmp_path / "trans.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.setFont("Helvetica", 12)
    c.drawString(72, 650, "translated by Jane Smith")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert len(m.creators) == 1
    assert m.creators[0].role == CreatorRole.TRANSLATOR


def test_pdf_extracts_publisher_places_date(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import WarningCode
    from tests.fixtures.pdf import build_pdf_with_imprint

    p = build_pdf_with_imprint(
        tmp_path / "imp.pdf",
        title="Sample",
        subtitle="Sub",
        isbn_paperback="9781234567897",
        isbn_hardback="9781234567880",
        publisher="Example Press",
        places=["London", "New York"],
        year=2003,
        first_published_year=2000,
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.publisher == "Example Press"
    assert m.places == ["London", "New York"]
    assert m.date == "2003"
    assert m.first_published == "2000"
    codes = {w.code for w in m.warnings}
    assert WarningCode.MULTIPLE_PLACES_DETECTED in codes


def test_pdf_single_year_first_published_none(tmp_path: Path) -> None:
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from tests.fixtures.pdf import build_pdf_with_imprint

    p = build_pdf_with_imprint(
        tmp_path / "one.pdf",
        title="Sample",
        subtitle="Sub",
        isbn_paperback="9781234567897",
        isbn_hardback="9781234567880",
        publisher="Example Press",
        places=["London"],
        year=2003,
        first_published_year=None,
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.date == "2003"
    assert m.first_published is None


def test_pdf_malformed_returns_error_with_warning(tmp_path: Path) -> None:
    """A non-PDF file ending in .pdf yields MALFORMED_PDF + INCOMPLETE_EXTRACTION."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import ErrorCode, WarningCode

    p = tmp_path / "notpdf.pdf"
    p.write_bytes(b"this is not a PDF file at all")
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.error == ErrorCode.MALFORMED_PDF
    assert WarningCode.INCOMPLETE_EXTRACTION in {w.code for w in m.warnings}


# ---------------------------------------------------------------------------
# Task 21 heuristic regression tests (synthetic fixtures)
# ---------------------------------------------------------------------------


def test_pdf_prefers_all_caps_over_info_title_when_same_words(tmp_path: Path) -> None:
    """ALL-CAPS text-mined title wins over mixed-case /Info /Title when words match."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import WarningCode

    p = build_pdf_with_info_and_all_caps(
        tmp_path / "caps_vs_info.pdf",
        info_title="The Sample Title",
        title_lines=["THE SAMPLE TITLE"],
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.title == "THE SAMPLE TITLE"
    assert WarningCode.TITLE_ALL_CAPS_IN_SOURCE in {w.code for w in m.warnings}


def test_pdf_imprint_scope_excludes_pages_beyond_4(tmp_path: Path) -> None:
    """Place names on page 6 are outside the 4-page imprint scope and are ignored."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = tmp_path / "scope.pdf"
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas as _canvas

    c = _canvas.Canvas(str(p), pagesize=LETTER)
    # Page 1: title page
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.showPage()
    # Pages 2-5: imprint / front matter (no place names)
    for label in ("Copyright © 2020", "Acknowledgements", "Contents", "Preface"):
        c.setFont("Helvetica", 10)
        c.drawString(72, 720, label)
        c.showPage()
    # Page 6 (index 5): body paragraph mentioning a city — must NOT be picked up
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "The conference was held in Chicago in 1995.")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.places == []


def test_pdf_publisher_prefers_shortest_matching_line(tmp_path: Path) -> None:
    """Publisher extraction picks the shortest line containing an imprint keyword."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = tmp_path / "pub_short.pdf"
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas as _canvas

    c = _canvas.Canvas(str(p), pagesize=LETTER)
    # Page 1: title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.showPage()
    # Page 2: imprint with two lines — long description and standalone name
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "First published by Verso Books in the United Kingdom")
    c.drawString(72, 706, "Verso")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.publisher == "Verso"


def test_pdf_extracts_all_caps_author_line(tmp_path: Path) -> None:
    """ALL-CAPS author name on its own line (no 'by' prefix, no comma form)."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = tmp_path / "allcaps.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "THE EXAMPLE BOOK")
    c.drawString(72, 670, "A SAMPLE SUBTITLE OF SUFFICIENT LENGTH")
    c.setFont("Helvetica", 12)
    c.drawString(72, 630, "JANE Q. SMITH")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert len(m.creators) == 1
    assert m.creators[0].last_name == "SMITH"
    assert m.creators[0].first_name == "JANE Q."


def test_pdf_edition_picks_latest_when_multiple(tmp_path: Path) -> None:
    """Multiple 'Nth Paperback Edition' phrases — latest wins."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p2 = tmp_path / "multi-edition2.pdf"
    c = canvas.Canvas(str(p2), pagesize=LETTER)
    c.setTitle("Multi")
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.showPage()
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "First paperback edition first published 2001")
    c.drawString(72, 700, "Second paperback edition first published 2003")
    c.drawString(72, 680, "Verso")
    c.drawString(72, 660, "London")
    c.drawString(72, 640, "Paperback ISBN 9781234567897")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p2)
    assert m.edition == "Second paperback edition"


def test_pdf_edition_hint_fallback_from_edition_phrase(tmp_path: Path) -> None:
    """Edition-hint is hoisted from the edition phrase when ISBN lines lack a window hint."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import EditionHint

    p = tmp_path / "edition_hint.pdf"
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas as _canvas

    c = _canvas.Canvas(str(p), pagesize=LETTER)
    # Page 1: title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.showPage()
    # Page 2: imprint — edition phrase + bare ISBNs (no per-line hint keywords)
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "Second Paperback Edition")
    c.drawString(72, 706, "Copyright © 2003")
    c.drawString(72, 692, "ISBN 9781234567897")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert len(m.identifier.candidates) >= 1
    assert all(
        cand.edition_hint == EditionHint.PAPERBACK
        for cand in m.identifier.candidates
    )


# ---------------------------------------------------------------------------
# Task 21 / 0021 regression tests — Beyond Chutzpah failure modes
# ---------------------------------------------------------------------------


def test_pdf_warns_incomplete_extraction_when_imprint_empty(tmp_path: Path) -> None:
    """PDF with title only and no imprint page fires INCOMPLETE_EXTRACTION."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor
    from book_ingestion.metadata import WarningCode

    p = tmp_path / "no_imprint.pdf"
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas as _canvas

    c = _canvas.Canvas(str(p), pagesize=LETTER)
    c.setTitle("Some Book Without Imprint")
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "SOME BOOK WITHOUT IMPRINT")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert WarningCode.INCOMPLETE_EXTRACTION in {w.code for w in m.warnings}
    assert m.publisher is None
    assert not m.places


def test_pdf_creator_rejects_title_fragment_in_all_caps(tmp_path: Path) -> None:
    """ALL-CAPS title banner on its own line must not be parsed as an author."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = tmp_path / "title_banner.pdf"
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas as _canvas

    c = _canvas.Canvas(str(p), pagesize=LETTER)
    # /Info /Title set so the extractor picks up the real title
    c.setTitle("Beyond Chutzpah: On the Misuse of History")
    # Page 1: only the ALL-CAPS title banner — no actual author block
    c.setFont("Helvetica-Bold", 24)
    c.drawString(72, 700, "BEYOND CHUTZPAH")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    # The title-fragment must NOT become a creator
    assert m.creators == []


def test_pdf_extracts_university_press_via_generic_pattern(tmp_path: Path) -> None:
    """Imprint page with 'University of California Press' is captured by generic regex."""
    from book_ingestion.extractors.pdf import PdfMetadataExtractor

    p = tmp_path / "uc_press.pdf"
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas as _canvas

    c = _canvas.Canvas(str(p), pagesize=LETTER)
    c.setTitle("Some UC Press Book")
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "SOME UC PRESS BOOK")
    c.showPage()
    # Page 2: imprint with UC Press line
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "University of California Press")
    c.drawString(72, 706, "Berkeley and Los Angeles, California")
    c.drawString(72, 692, "Copyright © 2005")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.publisher == "University of California Press"
