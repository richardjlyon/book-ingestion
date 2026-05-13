"""Tests for the BookMetadata Pydantic model and its sub-models."""
from __future__ import annotations

import pytest

from book_ingestion.ir import SCHEMA_VERSION
from book_ingestion.metadata import (
    BookMetadata,
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
        c.value = "other"


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


def test_book_metadata_defaults() -> None:
    m = BookMetadata()
    assert m.schema_version == SCHEMA_VERSION
    assert m.kind == "book_metadata"
    assert m.title is None
    assert m.creators == []
    assert m.places == []
    assert m.error is None
    assert m.warnings == []
    assert m.identifier.kind is None


def test_book_metadata_full() -> None:
    m = BookMetadata(
        identifier=Identifier(
            kind=IdentifierKind.ISBN,
            value="9781844674879",
            candidates=[
                IdentifierCandidate(
                    kind=IdentifierKind.ISBN,
                    value="9781844674879",
                    edition_hint=EditionHint.PAPERBACK,
                ),
            ],
        ),
        title="The Holocaust Industry",
        subtitle="Reflections on the Exploitation of Jewish Suffering",
        full_title="The Holocaust Industry: Reflections on the Exploitation of Jewish Suffering",
        creators=[Creator(first_name="Norman G.", last_name="Finkelstein")],
        publisher="Verso",
        places=["London", "New York"],
        date="2003",
        first_published="2000",
        edition="Second Paperback Edition",
        language="en",
        warnings=[MetadataWarning(code=WarningCode.TITLE_ALL_CAPS_IN_SOURCE)],
    )
    assert m.identifier.value == "9781844674879"
    assert m.full_title is not None
    assert m.full_title.startswith("The Holocaust Industry:")
    assert m.creators[0].last_name == "Finkelstein"


def test_book_metadata_json_round_trip() -> None:
    m = BookMetadata(
        title="X",
        identifier=Identifier(kind=IdentifierKind.ISBN, value="9780520295711"),
    )
    payload = m.model_dump(mode="json")
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "book_metadata"
    assert payload["title"] == "X"
    assert payload["identifier"]["kind"] == "isbn"
    assert payload["identifier"]["value"] == "9780520295711"
    assert payload["warnings"] == []
    assert payload["error"] is None

    again = BookMetadata.model_validate(payload)
    assert again == m


def test_book_metadata_error_excludes_other_fields_at_default() -> None:
    """When error is set, other fields stay at defaults (caller contract)."""
    m = BookMetadata(error=ErrorCode.ENCRYPTED)
    assert m.error == ErrorCode.ENCRYPTED
    assert m.title is None
    assert m.creators == []
    assert m.warnings == []
