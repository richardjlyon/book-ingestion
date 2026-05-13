"""Tests for EpubMetadataExtractor + supporting EPUB fixture helpers."""
from __future__ import annotations

from pathlib import Path

from book_ingestion.extractors.epub import EpubMetadataExtractor
from book_ingestion.metadata import BookMetadata, CreatorRole, ErrorCode, WarningCode
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
