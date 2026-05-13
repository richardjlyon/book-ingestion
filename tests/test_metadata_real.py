"""Real-fixture acceptance tests for extract_metadata.

These tests depend on files at known paths outside the repo. Marked
@slow and @real_book so they're deselected from routine runs.

If a future spec change shifts a pinned value, the test fails and forces
the change to be reviewed — that's the regression signal.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion import extract_metadata
from book_ingestion.metadata import EditionHint, IdentifierKind, WarningCode

_HOLOCAUST_INDUSTRY_PATH = Path(
    "/Users/rjl/Code/test-pdfs/"
    "The Holocaust Industry Reflections on the Exploitation of Jewish "
    "Suffering (Norman G. Finkelstein) (z-library.sk, 1lib.sk, z-lib.sk).pdf"
)


@pytest.mark.slow
@pytest.mark.real_book
def test_holocaust_industry_pdf_acceptance() -> None:
    if not _HOLOCAUST_INDUSTRY_PATH.exists():
        pytest.skip(f"fixture missing: {_HOLOCAUST_INDUSTRY_PATH}")

    m = extract_metadata(_HOLOCAUST_INDUSTRY_PATH)

    # Identifier — pinned: paperback ISBN as the chosen value
    assert m.identifier.kind == IdentifierKind.ISBN
    assert m.identifier.value == "9781844674879"
    paperback = next(
        (c for c in m.identifier.candidates if c.edition_hint == EditionHint.PAPERBACK), None,
    )
    assert paperback is not None

    # Title — pinned: raw ALL-CAPS, no normalisation
    assert m.title is not None
    assert m.title.isupper()
    assert "HOLOCAUST INDUSTRY" in m.title

    # Subtitle — pinned: raw ALL-CAPS
    assert m.subtitle is not None
    assert m.subtitle.isupper()
    assert "EXPLOITATION" in m.subtitle

    # full_title composed
    assert m.full_title == f"{m.title}: {m.subtitle}"

    # Warnings
    codes = {w.code for w in m.warnings}
    assert WarningCode.TITLE_ALL_CAPS_IN_SOURCE in codes
    # ISBN-10 / ISBN-13 dedupe should keep MULTIPLE_ISBNS_DETECTED quiet
    assert WarningCode.MULTIPLE_ISBNS_DETECTED not in codes

    # Creator — ALL-CAPS on a standalone line on page 1
    assert len(m.creators) >= 1
    assert m.creators[0].last_name == "FINKELSTEIN"
    # first_name is "NORMAN G." (raw ALL-CAPS preserved)
    assert m.creators[0].first_name is not None
    assert "NORMAN" in m.creators[0].first_name
    assert "G" in m.creators[0].first_name  # the initial

    # Edition — latest of "First paperback edition" / "Second paperback edition"
    # The PDF source has lowercase "second paperback edition"; case is preserved.
    assert m.edition is not None
    assert "second" in m.edition.lower()
    assert "paperback" in m.edition.lower()

    # Publication
    assert m.publisher == "Verso"
    assert m.places == ["London", "New York"]
    assert m.date == "2003"
    assert m.first_published == "2000"


_GAZA_EPUB_PATH = Path(
    "/Users/rjl/Code/test-pdfs/"
    "Gaza - An Inquest Into Its Martyrdom (2018) (Norman Finkelstein) "
    "(z-library.sk, 1lib.sk, z-lib.sk).epub"
)


@pytest.mark.slow
@pytest.mark.real_book
def test_gaza_epub_acceptance() -> None:
    if not _GAZA_EPUB_PATH.exists():
        pytest.skip(f"fixture missing: {_GAZA_EPUB_PATH}")

    m = extract_metadata(_GAZA_EPUB_PATH)

    # Identifier — print ISBN
    assert m.identifier.kind == IdentifierKind.ISBN
    assert m.identifier.value == "9780520295711"
    # eISBN as a candidate with EBOOK hint
    eisbn = next(
        (c for c in m.identifier.candidates if c.edition_hint == EditionHint.EBOOK), None,
    )
    assert eisbn is not None

    # Title / subtitle — fallback supplied the subtitle from title-page xhtml
    assert m.title == "Gaza"
    assert m.subtitle == "An Inquest Into Its Martyrdom"
    assert m.full_title == "Gaza: An Inquest Into Its Martyrdom"

    # Creator — Finkelstein, Norman with trailing punctuation in raw
    assert len(m.creators) == 1
    assert m.creators[0].last_name == "Finkelstein"
    assert m.creators[0].first_name == "Norman"
    assert m.creators[0].raw is not None
    assert m.creators[0].raw.endswith("; ") or m.creators[0].raw.endswith(";")

    # Language normalised
    assert m.language == "en"

    # Warnings pinned
    codes = {w.code for w in m.warnings}
    assert WarningCode.LANGUAGE_NORMALISED in codes
    assert WarningCode.DC_CREATOR_TRAILING_PUNCTUATION in codes
    assert WarningCode.SUBTITLE_NOT_IN_OPF in codes
