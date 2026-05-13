"""Book metadata schema and helpers.

Returned by `book_ingestion.extract_metadata()`. See
`docs/superpowers/specs/2026-05-13-extract-metadata-design.md` for the full
shape and contract.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IdentifierKind(StrEnum):
    ISBN = "isbn"
    DOI = "doi"
    ARXIV = "arxiv"


class EditionHint(StrEnum):
    PAPERBACK = "paperback"
    HARDBACK = "hardback"
    EBOOK = "ebook"
    UNSPECIFIED = "unspecified"


class CreatorRole(StrEnum):
    AUTHOR = "author"
    EDITOR = "editor"
    TRANSLATOR = "translator"
    FOREWORD = "foreword"
    ILLUSTRATOR = "illustrator"


class ErrorCode(StrEnum):
    ENCRYPTED = "encrypted"
    DRM_PROTECTED = "drm_protected"
    MALFORMED_PDF = "malformed_pdf"
    MALFORMED_EPUB = "malformed_epub"


class WarningCode(StrEnum):
    TITLE_ALL_CAPS_IN_SOURCE = "title_all_caps_in_source"
    SUBTITLE_NOT_IN_OPF = "subtitle_not_in_opf"
    MULTIPLE_ISBNS_DETECTED = "multiple_isbns_detected"
    DC_CREATOR_TRAILING_PUNCTUATION = "dc_creator_trailing_punctuation"
    LANGUAGE_NORMALISED = "language_normalised"
    NO_TEXT_EXTRACTED = "no_text_extracted"
    INCOMPLETE_EXTRACTION = "incomplete_extraction"
    MULTIPLE_PLACES_DETECTED = "multiple_places_detected"


class IdentifierCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: IdentifierKind
    value: str
    edition_hint: EditionHint = EditionHint.UNSPECIFIED


class Identifier(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: IdentifierKind | None = None
    value: str | None = None
    candidates: list[IdentifierCandidate] = Field(default_factory=list)


class Creator(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: CreatorRole = CreatorRole.AUTHOR
    first_name: str | None = None
    last_name: str | None = None
    raw: str | None = None


class MetadataWarning(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: WarningCode
    detail: str | None = None
