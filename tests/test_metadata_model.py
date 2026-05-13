"""Tests for the BookMetadata Pydantic model and its sub-models."""
from __future__ import annotations

import pytest

from book_ingestion.metadata import (
    Creator,
    CreatorRole,
    EditionHint,
    ErrorCode,
    Identifier,
    IdentifierCandidate,
    IdentifierKind,
    MetadataWarning,
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


def test_identifier_candidate_defaults() -> None:
    c = IdentifierCandidate(kind=IdentifierKind.ISBN, value="9781844674879")
    assert c.kind == IdentifierKind.ISBN
    assert c.value == "9781844674879"
    assert c.edition_hint == EditionHint.UNSPECIFIED


def test_identifier_candidate_frozen() -> None:
    import pydantic
    c = IdentifierCandidate(kind=IdentifierKind.ISBN, value="9781844674879")
    with pytest.raises(pydantic.ValidationError):
        c.value = "other"  # type: ignore[misc]


def test_identifier_defaults() -> None:
    i = Identifier()
    assert i.kind is None
    assert i.value is None
    assert i.candidates == []


def test_creator_defaults() -> None:
    c = Creator()
    assert c.role == CreatorRole.AUTHOR
    assert c.first_name is None
    assert c.last_name is None
    assert c.raw is None


def test_creator_with_fields() -> None:
    c = Creator(
        role=CreatorRole.TRANSLATOR,
        first_name="Norman G.",
        last_name="Finkelstein",
        raw="Finkelstein, Norman; ",
    )
    assert c.last_name == "Finkelstein"
    assert c.raw == "Finkelstein, Norman; "


def test_metadata_warning() -> None:
    w = MetadataWarning(code=WarningCode.LANGUAGE_NORMALISED, detail="en-US -> en")
    assert w.code == WarningCode.LANGUAGE_NORMALISED
    assert w.detail == "en-US -> en"


def test_metadata_warning_no_detail() -> None:
    w = MetadataWarning(code=WarningCode.SUBTITLE_NOT_IN_OPF)
    assert w.detail is None
