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

    # Publication
    assert m.publisher == "Verso"
    assert m.places == ["London", "New York"]
    assert m.date == "2003"
    assert m.first_published == "2000"
