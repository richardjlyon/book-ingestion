"""Tests for EpubMetadataExtractor + supporting EPUB fixture helpers."""
from __future__ import annotations

from pathlib import Path

from book_ingestion.extractors.epub import EpubMetadataExtractor
from book_ingestion.metadata import (
    BookMetadata,
    CreatorRole,
    EditionHint,
    ErrorCode,
    IdentifierKind,
    WarningCode,
)
from tests.fixtures.epub import (
    build_epub,
    build_epub_with_drm,
    build_epub_with_truncated_title,
    build_malformed_epub,
)


def test_epub_fixture_basic_builds(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "basic.epub",
        dc_title="Sample Book",
        creators=[("Smith, Jane", "aut")],
        isbn="9781234567897",
        publisher="Example Press",
        language="en",
    )
    assert p.exists() and p.stat().st_size > 500


def test_epub_fixture_truncated_title_builds(tmp_path: Path) -> None:
    p = build_epub_with_truncated_title(
        tmp_path / "trunc.epub",
        dc_title="Gaza",
        full_title_in_xhtml="Gaza: An Inquest Into Its Martyrdom",
    )
    assert p.exists()


def test_epub_fixture_drm_builds(tmp_path: Path) -> None:
    p = build_epub_with_drm(tmp_path / "drm.epub")
    assert p.exists()


def test_epub_fixture_malformed_builds(tmp_path: Path) -> None:
    p = build_malformed_epub(tmp_path / "bad.epub")
    assert p.exists()


def test_epub_drm_returns_error(tmp_path: Path) -> None:
    p = build_epub_with_drm(tmp_path / "drm.epub")
    m = EpubMetadataExtractor().extract_metadata(p)
    assert isinstance(m, BookMetadata)
    assert m.error == ErrorCode.DRM_PROTECTED
    assert m.title is None


def test_epub_malformed_no_container_returns_error(tmp_path: Path) -> None:
    p = build_malformed_epub(tmp_path / "bad.epub")
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.error == ErrorCode.MALFORMED_EPUB


def test_epub_not_a_zip_returns_error(tmp_path: Path) -> None:
    p = tmp_path / "notzip.epub"
    p.write_bytes(b"this is not a zip file")
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.error == ErrorCode.MALFORMED_EPUB


def test_epub_extracts_dc_title(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "t.epub",
        dc_title="Sample Book",
        creators=[("Smith, Jane", "aut")],
        isbn=None,
        publisher=None,
        language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.title == "Sample Book"
    assert m.full_title == "Sample Book"


def test_epub_extracts_publisher(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "pub.epub",
        dc_title="X",
        creators=[],
        isbn=None,
        publisher="Example Press",
        language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.publisher == "Example Press"


def test_epub_normalises_language_and_flags(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "lang.epub",
        dc_title="X",
        creators=[],
        isbn=None,
        publisher=None,
        language="en-US",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.language == "en"
    codes = {w.code for w in m.warnings}
    assert WarningCode.LANGUAGE_NORMALISED in codes


def test_epub_language_no_normalisation_no_flag(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "lang2.epub",
        dc_title="X",
        creators=[],
        isbn=None,
        publisher=None,
        language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.language == "en"
    codes = {w.code for w in m.warnings}
    assert WarningCode.LANGUAGE_NORMALISED not in codes


def test_epub_creator_with_role_aut(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "aut.epub",
        dc_title="X",
        creators=[("Finkelstein, Norman", "aut")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert len(m.creators) == 1
    assert m.creators[0].role == CreatorRole.AUTHOR
    assert m.creators[0].last_name == "Finkelstein"
    assert m.creators[0].first_name == "Norman"
    assert m.creators[0].raw == "Finkelstein, Norman"


def test_epub_creator_trailing_semicolon_flagged(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "ts.epub",
        dc_title="X",
        creators=[("Finkelstein, Norman; ", "aut")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.creators[0].last_name == "Finkelstein"
    assert m.creators[0].raw == "Finkelstein, Norman; "
    codes = {w.code for w in m.warnings}
    assert WarningCode.DC_CREATOR_TRAILING_PUNCTUATION in codes


def test_epub_creator_trailing_period_silent(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "tp.epub",
        dc_title="X",
        creators=[("Smith, J.", "aut")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.creators[0].last_name == "Smith"
    assert m.creators[0].first_name == "J"
    codes = {w.code for w in m.warnings}
    assert WarningCode.DC_CREATOR_TRAILING_PUNCTUATION not in codes


def test_epub_creator_role_translator(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "tr.epub",
        dc_title="X",
        creators=[("Translator, T.", "trl")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.creators[0].role == CreatorRole.TRANSLATOR


def test_epub_creator_multi_creator_in_one_string(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "multi.epub",
        dc_title="X",
        creators=[("Smith, J. and Jones, K.", "aut")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert [c.last_name for c in m.creators] == ["Smith", "Jones"]


def test_epub_creator_order_preserved(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "order.epub",
        dc_title="X",
        creators=[("Smith, Jane", "aut"), ("Jones, John", "aut")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert [c.last_name for c in m.creators] == ["Smith", "Jones"]


def test_epub_extracts_print_isbn(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "isbn.epub",
        dc_title="X",
        creators=[],
        isbn="9780520295711",
        publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.identifier.kind == IdentifierKind.ISBN
    assert m.identifier.value == "9780520295711"


def test_epub_eisbn_in_candidates_with_ebook_hint(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "ei.epub",
        dc_title="X",
        creators=[],
        isbn="9780520295711",
        eisbn="9780520968431",
        publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.identifier.value == "9780520295711"
    eisbn_candidate = next(
        (c for c in m.identifier.candidates if c.value == "9780520968431"), None,
    )
    assert eisbn_candidate is not None
    assert eisbn_candidate.edition_hint == EditionHint.EBOOK


def test_epub_eisbn_only_becomes_value(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "eonly.epub",
        dc_title="X",
        creators=[],
        isbn=None,
        eisbn="9780520968431",
        publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.identifier.value == "9780520968431"


def test_epub_date_with_publication_event(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "d.epub",
        dc_title="X", creators=[], isbn=None, publisher=None,
        language="en", date="2018",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.date == "2018"


def test_epub_date_from_rights_year_when_no_dc_date(tmp_path: Path) -> None:
    # build a custom OPF with dc:rights but no dc:date
    p = tmp_path / "rights.epub"
    opf = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="b">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>X</dc:title>
    <dc:language>en</dc:language>
    <dc:rights>Copyright © 2018 by Author</dc:rights>
  </metadata>
  <manifest><item id="t" href="t.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="t"/></spine>
</package>"""
    import zipfile as _zf
    with _zf.ZipFile(p, "w", _zf.ZIP_DEFLATED) as zf:
        zf.writestr(_zf.ZipInfo("mimetype"), "application/epub+zip", compress_type=_zf.ZIP_STORED)
        zf.writestr("META-INF/container.xml",
                    '<?xml version="1.0"?><container version="1.0" '
                    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                    '<rootfile full-path="OEBPS/content.opf" '
                    'media-type="application/oebps-package+xml"/></rootfiles></container>')
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/t.xhtml", "<html/>")

    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.date == "2018"


def test_epub_title_page_fallback_supplies_subtitle(tmp_path: Path) -> None:
    p = build_epub_with_truncated_title(
        tmp_path / "fallback.epub",
        dc_title="Gaza",
        full_title_in_xhtml="Gaza: An Inquest Into Its Martyrdom",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.title == "Gaza"
    assert m.subtitle == "An Inquest Into Its Martyrdom"
    assert m.full_title == "Gaza: An Inquest Into Its Martyrdom"
    codes = {w.code for w in m.warnings}
    assert WarningCode.SUBTITLE_NOT_IN_OPF in codes


def test_epub_title_page_no_fallback_when_dc_title_complete(tmp_path: Path) -> None:
    """If dc:title already contains a colon-delimited subtitle, don't fall back."""
    p = build_epub(
        tmp_path / "complete.epub",
        dc_title="Gaza: An Inquest Into Its Martyrdom",
        creators=[], isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    # The extractor may parse "Gaza: An Inquest..." as title; subtitle handling
    # at the dc:title level is out of scope for M2.0 (just title=full string).
    # What matters: no SUBTITLE_NOT_IN_OPF warning.
    codes = {w.code for w in m.warnings}
    assert WarningCode.SUBTITLE_NOT_IN_OPF not in codes
