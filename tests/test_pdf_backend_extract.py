"""Tests for the PDF backend's extract_chapter() path."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion.backends.base import Context
from book_ingestion.backends.pdf_docling import PdfDoclingBackend
from book_ingestion.cache import Cache


@pytest.mark.slow
def test_extract_chapter_returns_simple_view(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    backend = PdfDoclingBackend()
    ctx = Context(cache=Cache(root=tmp_cache_dir))
    survey = backend.survey(synthetic_pdf, ctx=ctx)

    if not survey.chapters:
        pytest.skip("Docling found no chapters in the synthetic PDF; covered by real-book test")

    content = backend.extract_chapter(synthetic_pdf, 0, ctx=ctx)
    assert content.chapter.index == 0
    assert content.quality.backend == "docling_pdf"
    types = {b.type for b in content.simple_view}
    assert types - {"page_break"}, "no content blocks produced"


@pytest.mark.slow
def test_extract_chapter_index_out_of_range_raises(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    backend = PdfDoclingBackend()
    ctx = Context(cache=Cache(root=tmp_cache_dir))
    backend.survey(synthetic_pdf, ctx=ctx)

    with pytest.raises(IndexError):
        backend.extract_chapter(synthetic_pdf, 9999, ctx=ctx)
