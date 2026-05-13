"""Tests for the BookMetadata Pydantic model and its sub-models."""
from __future__ import annotations

from book_ingestion.metadata import (
    CreatorRole,
    EditionHint,
    ErrorCode,
    IdentifierKind,
    WarningCode,
)


def test_imports() -> None:
    from book_ingestion import metadata
    from book_ingestion.extractors import base
    assert metadata is not None
    assert base is not None


def test_identifier_kind_members() -> None:
    assert {k.value for k in IdentifierKind} == {"isbn", "doi", "arxiv"}


def test_edition_hint_members() -> None:
    assert {e.value for e in EditionHint} == {
        "paperback",
        "hardback",
        "ebook",
        "unspecified",
    }


def test_creator_role_members() -> None:
    assert {r.value for r in CreatorRole} == {
        "author",
        "editor",
        "translator",
        "foreword",
        "illustrator",
    }


def test_error_code_members() -> None:
    assert {e.value for e in ErrorCode} == {
        "encrypted",
        "drm_protected",
        "malformed_pdf",
        "malformed_epub",
    }


def test_warning_code_members() -> None:
    assert {w.value for w in WarningCode} == {
        "title_all_caps_in_source",
        "subtitle_not_in_opf",
        "multiple_isbns_detected",
        "dc_creator_trailing_punctuation",
        "language_normalised",
        "no_text_extracted",
        "incomplete_extraction",
        "multiple_places_detected",
    }
