"""Book metadata schema and helpers.

Returned by `book_ingestion.extract_metadata()`. See
`docs/superpowers/specs/2026-05-13-extract-metadata-design.md` for the full
shape and contract.
"""
from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from book_ingestion.ir import SCHEMA_VERSION


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


class BookMetadata(BaseModel):
    schema_version: str = SCHEMA_VERSION
    kind: Literal["book_metadata"] = "book_metadata"

    # Identifier
    identifier: Identifier = Field(default_factory=Identifier)

    # Title
    title: str | None = None
    subtitle: str | None = None
    full_title: str | None = None

    # Authorship
    creators: list[Creator] = Field(default_factory=list)

    # Publication
    publisher: str | None = None
    places: list[str] = Field(default_factory=list)
    date: str | None = None
    first_published: str | None = None
    edition: str | None = None

    # Other
    language: str | None = None

    # Diagnostics
    error: ErrorCode | None = None
    warnings: list[MetadataWarning] = Field(default_factory=list)


# --- ISBN helpers -----------------------------------------------------------

_ISBN_SEPARATOR_RE = re.compile(r"[-\s]")


def canonicalize_isbn(raw: str) -> str:
    """Strip separators from an ISBN string, leaving digits (and optional final 'X')."""
    return _ISBN_SEPARATOR_RE.sub("", raw).upper()


def isbn10_to_isbn13(isbn10: str) -> str:
    """Convert a canonicalized 10-digit ISBN to its 13-digit form (978-prefixed).

    Raises ValueError when the input is not a 10-character ISBN-10.
    """
    if len(isbn10) != 10:
        raise ValueError(f"not an ISBN-10 (length {len(isbn10)}): {isbn10!r}")
    body = "978" + isbn10[:9]
    # ISBN-13 check digit: weighted sum (1,3,1,3,...) over the 12 leading digits,
    # then (10 - sum mod 10) mod 10.
    weights = [1, 3] * 6
    total = sum(int(d) * w for d, w in zip(body, weights, strict=True))
    check = (10 - (total % 10)) % 10
    return body + str(check)


def dedupe_isbn_candidates(
    candidates: list[IdentifierCandidate],
) -> list[IdentifierCandidate]:
    """Collapse ISBN-10 / ISBN-13 same-edition pairs.

    For each non-ISBN candidate: pass through. For each ISBN candidate:
    canonicalize to ISBN-13. If two candidates resolve to the same ISBN-13,
    keep the one whose value is already in ISBN-13 form. On edition-hint
    conflict, prefer the non-UNSPECIFIED hint; if both are specified and
    differ, prefer the ISBN-13 form's hint.
    """
    by_key: dict[str, tuple[IdentifierKind, IdentifierCandidate]] = {}
    for cand in candidates:
        if cand.kind != IdentifierKind.ISBN:
            key = f"{cand.kind}:{cand.value}"
            if key not in by_key:
                by_key[key] = (cand.kind, cand)
            continue

        # ISBN: compute ISBN-13 key
        canon = cand.value
        try:
            key_val = canon if len(canon) == 13 else isbn10_to_isbn13(canon)
        except ValueError:
            # Malformed ISBN — keep as-is, don't merge.
            key = f"{IdentifierKind.ISBN}:{canon}"
            by_key[key] = (IdentifierKind.ISBN, cand)
            continue

        key = f"{IdentifierKind.ISBN}:{key_val}"
        existing = by_key.get(key)
        if existing is None:
            # Promote to ISBN-13 form if we're an ISBN-10
            if len(canon) == 10:
                by_key[key] = (IdentifierKind.ISBN, cand.model_copy(update={"value": key_val}))
            else:
                by_key[key] = (IdentifierKind.ISBN, cand)
            continue

        # Merge: ISBN-13 form wins on value; edition hint preference rules.
        winner_value = key_val  # always ISBN-13 in dedupe output
        # hint preference:
        existing_hint = existing[1].edition_hint
        new_hint = cand.edition_hint
        if existing_hint == EditionHint.UNSPECIFIED and new_hint != EditionHint.UNSPECIFIED:
            chosen_hint: EditionHint = new_hint
        elif new_hint == EditionHint.UNSPECIFIED and existing_hint != EditionHint.UNSPECIFIED:
            chosen_hint = existing_hint
        elif len(cand.value) == 13:
            chosen_hint = new_hint
        else:
            chosen_hint = existing_hint
        by_key[key] = (
            IdentifierKind.ISBN,
            IdentifierCandidate(
                kind=IdentifierKind.ISBN,
                value=winner_value,
                edition_hint=chosen_hint,
            ),
        )

    return [v[1] for v in by_key.values()]


# --- Edition hint classification and priority picking -----------------------

_PAPERBACK_KEYWORDS = ("paperback", "pbk", "softcover", "trade paperback")
# " hb " (bare two-letter token) handled below via padded-bookend check —
# substring match alone can't differentiate "hb" from "kombucha".
_HARDBACK_KEYWORDS = ("hardback", "hardcover", "cloth")
_EBOOK_KEYWORDS = ("pdf", "ebook", "kindle", "epub", "digital")


def classify_edition_hint(text: str) -> EditionHint:
    """Classify an edition from surrounding text (case-insensitive).

    Used on a ~80-character window around each ISBN match. See spec §5.2.
    """
    lowered = text.lower()
    if any(kw in lowered for kw in _PAPERBACK_KEYWORDS):
        return EditionHint.PAPERBACK
    if any(kw in lowered for kw in _HARDBACK_KEYWORDS) or " hb " in f" {lowered} ":
        return EditionHint.HARDBACK
    if any(kw in lowered for kw in _EBOOK_KEYWORDS):
        return EditionHint.EBOOK
    return EditionHint.UNSPECIFIED


_EDITION_PRIORITY: tuple[EditionHint, ...] = (
    EditionHint.PAPERBACK,
    EditionHint.HARDBACK,
    EditionHint.UNSPECIFIED,
    EditionHint.EBOOK,
)


def pick_identifier_value(candidates: list[IdentifierCandidate]) -> str | None:
    """Choose the best candidate's value according to PAPERBACK > HARDBACK > UNSPECIFIED > EBOOK."""
    for tier in _EDITION_PRIORITY:
        for cand in candidates:
            if cand.edition_hint == tier:
                return cand.value
    return None
