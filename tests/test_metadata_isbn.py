"""Tests for ISBN canonicalization, ISBN-10 to ISBN-13 conversion, and dedupe."""
from __future__ import annotations

import pytest

from book_ingestion.metadata import (
    EditionHint,
    IdentifierCandidate,
    IdentifierKind,
    canonicalize_isbn,
    dedupe_isbn_candidates,
    isbn10_to_isbn13,
)

# --- canonicalize_isbn -------------------------------------------------------

def test_canonicalize_strips_hyphens() -> None:
    assert canonicalize_isbn("978-1-84467-487-9") == "9781844674879"


def test_canonicalize_strips_spaces() -> None:
    assert canonicalize_isbn("978 1 84467 487 9") == "9781844674879"


def test_canonicalize_preserves_X() -> None:
    assert canonicalize_isbn("0-306-40615-X") == "030640615X"


def test_canonicalize_isbn10_already_clean() -> None:
    assert canonicalize_isbn("1844674878") == "1844674878"


# --- isbn10_to_isbn13 --------------------------------------------------------

def test_isbn10_to_isbn13_basic() -> None:
    # 1-84467-487-8 (ISBN-10) -> 978-1-84467-487-9 (ISBN-13)
    assert isbn10_to_isbn13("1844674878") == "9781844674879"


def test_isbn10_to_isbn13_check_digit_recompute() -> None:
    # 0-306-40615-2 -> 978-0-306-40615-7 (worked example from ISBN standard)
    assert isbn10_to_isbn13("0306406152") == "9780306406157"


def test_isbn10_to_isbn13_with_X_check_digit() -> None:
    # 0-19-852663-X -> 978-0-19-852663-6
    assert isbn10_to_isbn13("019852663X") == "9780198526636"


def test_isbn10_to_isbn13_rejects_non_isbn10() -> None:
    with pytest.raises(ValueError):
        isbn10_to_isbn13("9781844674879")  # already ISBN-13


# --- dedupe_isbn_candidates --------------------------------------------------

def test_dedupe_collapses_isbn10_and_isbn13_same_book() -> None:
    candidates = [
        IdentifierCandidate(
            kind=IdentifierKind.ISBN,
            value="1844674878",
            edition_hint=EditionHint.PAPERBACK,
        ),
        IdentifierCandidate(
            kind=IdentifierKind.ISBN,
            value="9781844674879",
            edition_hint=EditionHint.PAPERBACK,
        ),
    ]
    deduped = dedupe_isbn_candidates(candidates)
    assert len(deduped) == 1
    assert deduped[0].value == "9781844674879"  # ISBN-13 form wins
    assert deduped[0].edition_hint == EditionHint.PAPERBACK


def test_dedupe_preserves_distinct_editions() -> None:
    candidates = [
        IdentifierCandidate(
            kind=IdentifierKind.ISBN, value="9781844674879", edition_hint=EditionHint.PAPERBACK
        ),
        IdentifierCandidate(
            kind=IdentifierKind.ISBN, value="9781844677115", edition_hint=EditionHint.HARDBACK
        ),
    ]
    deduped = dedupe_isbn_candidates(candidates)
    assert len(deduped) == 2


def test_dedupe_edition_hint_from_isbn13_form_wins_on_conflict() -> None:
    candidates = [
        IdentifierCandidate(
            kind=IdentifierKind.ISBN, value="1844674878", edition_hint=EditionHint.UNSPECIFIED
        ),
        IdentifierCandidate(
            kind=IdentifierKind.ISBN, value="9781844674879", edition_hint=EditionHint.PAPERBACK
        ),
    ]
    deduped = dedupe_isbn_candidates(candidates)
    assert len(deduped) == 1
    assert deduped[0].edition_hint == EditionHint.PAPERBACK
