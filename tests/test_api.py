"""Tests for the public API."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion import extract_chapter, survey
from book_ingestion.ir import BookSurvey, ChapterContent


@pytest.mark.slow
def test_survey_public(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    s = survey(synthetic_pdf, cache_dir=tmp_cache_dir)
    assert isinstance(s, BookSurvey)
    assert s.source.format == "pdf"


@pytest.mark.slow
def test_extract_chapter_public(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    s = survey(synthetic_pdf, cache_dir=tmp_cache_dir)
    if not s.chapters:
        pytest.skip("Docling produced no chapters on the synthetic PDF.")
    c = extract_chapter(synthetic_pdf, 0, cache_dir=tmp_cache_dir)
    assert isinstance(c, ChapterContent)
    assert c.chapter.index == 0


def test_survey_rejects_unsupported_format(tmp_path: Path, tmp_cache_dir: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_bytes(b"plain")
    with pytest.raises(ValueError, match="unsupported format"):
        survey(p, cache_dir=tmp_cache_dir)
