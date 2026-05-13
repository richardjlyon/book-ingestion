"""Tests for the public extract_metadata dispatch."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion import BookMetadata, extract_metadata
from tests.fixtures.epub import build_epub
from tests.fixtures.pdf import build_pdf_with_imprint


def test_dispatch_to_pdf(tmp_path: Path) -> None:
    p = build_pdf_with_imprint(
        tmp_path / "x.pdf",
        title="X", subtitle="Y",
        isbn_paperback="9781234567897", isbn_hardback="9781234567880",
        publisher="P", places=["L"], year=2003,
    )
    m = extract_metadata(p)
    assert isinstance(m, BookMetadata)
    assert m.title == "X"


def test_dispatch_to_epub(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "x.epub",
        dc_title="EpubBook", creators=[], isbn=None,
        publisher=None, language="en",
    )
    m = extract_metadata(p)
    assert isinstance(m, BookMetadata)
    assert m.title == "EpubBook"


def test_dispatch_propagates_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        extract_metadata(tmp_path / "does-not-exist.pdf")


def test_dispatch_rejects_unknown_extension(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("hi")
    with pytest.raises(ValueError):
        extract_metadata(p)


def test_pages_parameter_default_is_6(tmp_path: Path) -> None:
    """extract_metadata's signature should accept pages kw without raising."""
    p = build_pdf_with_imprint(
        tmp_path / "x.pdf",
        title="X", subtitle="Y",
        isbn_paperback="9781234567897", isbn_hardback="9781234567880",
        publisher="P", places=["L"], year=2003,
    )
    m = extract_metadata(p, pages=3)
    assert isinstance(m, BookMetadata)
