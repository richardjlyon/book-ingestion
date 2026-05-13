"""Tests for edition-hint classification and priority picking."""
from __future__ import annotations

from book_ingestion.metadata import (
    EditionHint,
    IdentifierCandidate,
    IdentifierKind,
    classify_edition_hint,
    pick_identifier_value,
)

# --- classify_edition_hint ---------------------------------------------------

def test_classify_paperback() -> None:
    assert classify_edition_hint("paperback ISBN 9781844674879") == EditionHint.PAPERBACK


def test_classify_pbk_short() -> None:
    assert classify_edition_hint("(pbk) 9781844674879") == EditionHint.PAPERBACK


def test_classify_softcover() -> None:
    assert classify_edition_hint("Softcover edition 9781844674879") == EditionHint.PAPERBACK


def test_classify_trade_paperback() -> None:
    assert classify_edition_hint("Trade Paperback 9781844674879") == EditionHint.PAPERBACK


def test_classify_hardback() -> None:
    assert classify_edition_hint("Hardback ISBN 9781844674879") == EditionHint.HARDBACK


def test_classify_hardcover() -> None:
    assert classify_edition_hint("978-1-84467-487-9 hardcover") == EditionHint.HARDBACK


def test_classify_cloth() -> None:
    assert classify_edition_hint("9781844674879 cloth") == EditionHint.HARDBACK


def test_classify_ebook() -> None:
    assert classify_edition_hint("ebook ISBN 9781844674879") == EditionHint.EBOOK


def test_classify_kindle() -> None:
    assert classify_edition_hint("Kindle: 9781844674879") == EditionHint.EBOOK


def test_classify_epub() -> None:
    assert classify_edition_hint("9781844674879 (EPUB)") == EditionHint.EBOOK


def test_classify_pdf() -> None:
    assert classify_edition_hint("9781844674879 PDF edition") == EditionHint.EBOOK


def test_classify_no_match() -> None:
    assert classify_edition_hint("Some random text 9781844674879") == EditionHint.UNSPECIFIED


def test_classify_case_insensitive() -> None:
    assert classify_edition_hint("PAPERBACK") == EditionHint.PAPERBACK


# --- pick_identifier_value ---------------------------------------------------

def _isbn(value: str, hint: EditionHint = EditionHint.UNSPECIFIED) -> IdentifierCandidate:
    return IdentifierCandidate(kind=IdentifierKind.ISBN, value=value, edition_hint=hint)


def test_priority_paperback_wins() -> None:
    candidates = [
        _isbn("9781111111111", EditionHint.HARDBACK),
        _isbn("9782222222222", EditionHint.PAPERBACK),
        _isbn("9783333333333", EditionHint.UNSPECIFIED),
        _isbn("9784444444444", EditionHint.EBOOK),
    ]
    assert pick_identifier_value(candidates) == "9782222222222"


def test_priority_hardback_when_no_paperback() -> None:
    candidates = [
        _isbn("9781111111111", EditionHint.UNSPECIFIED),
        _isbn("9782222222222", EditionHint.HARDBACK),
        _isbn("9783333333333", EditionHint.EBOOK),
    ]
    assert pick_identifier_value(candidates) == "9782222222222"


def test_priority_unspecified_when_no_paperback_or_hardback() -> None:
    candidates = [
        _isbn("9781111111111", EditionHint.EBOOK),
        _isbn("9782222222222", EditionHint.UNSPECIFIED),
    ]
    assert pick_identifier_value(candidates) == "9782222222222"


def test_priority_ebook_last_resort() -> None:
    candidates = [_isbn("9781111111111", EditionHint.EBOOK)]
    assert pick_identifier_value(candidates) == "9781111111111"


def test_priority_empty_returns_none() -> None:
    assert pick_identifier_value([]) is None


def test_priority_first_in_tier_wins() -> None:
    candidates = [
        _isbn("9781111111111", EditionHint.PAPERBACK),
        _isbn("9782222222222", EditionHint.PAPERBACK),
    ]
    assert pick_identifier_value(candidates) == "9781111111111"
