"""Tests for the format sniffer."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion.detect import detect_format


def test_detect_pdf_by_magic_and_extension(tmp_path: Path) -> None:
    p = tmp_path / "book.pdf"
    p.write_bytes(b"%PDF-1.7\nrest")
    assert detect_format(p) == "pdf"


def test_detect_epub_by_extension_and_zip_magic(tmp_path: Path) -> None:
    p = tmp_path / "book.epub"
    p.write_bytes(b"PK\x03\x04rest_of_zip")
    assert detect_format(p) == "epub"


def test_detect_rejects_unsupported(tmp_path: Path) -> None:
    p = tmp_path / "book.txt"
    p.write_bytes(b"plain text")
    with pytest.raises(ValueError, match="unsupported format"):
        detect_format(p)


def test_detect_rejects_extension_mismatch(tmp_path: Path) -> None:
    p = tmp_path / "book.pdf"
    p.write_bytes(b"not a pdf")
    with pytest.raises(ValueError, match="not a valid PDF"):
        detect_format(p)
