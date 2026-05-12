"""End-to-end acceptance test against the real book in test/."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion import extract_chapter, survey
from book_ingestion.ir import Confidence, PageRange, Provenance

BOOK = Path(__file__).parent.parent / "test" / "What is Modern Israel (Yakov M. Rabkin) (z-library.sk, 1lib.sk, z-lib.sk).pdf"


pytestmark = [pytest.mark.slow, pytest.mark.real_book]


def _has_book() -> bool:
    return BOOK.exists()


@pytest.mark.skipif(not _has_book(), reason="real book file not present at test/")
def test_survey_returns_valid_book_survey(tmp_cache_dir: Path) -> None:
    s = survey(BOOK, cache_dir=tmp_cache_dir)
    assert s.kind == "book_survey"
    assert s.source.format == "pdf"
    assert s.source.size_bytes > 100_000  # 4.5MB book
    assert s.quality.pages_total is not None and s.quality.pages_total > 100
    assert s.map.provenance in {
        Provenance.EMBEDDED,
        Provenance.INFERRED,
        Provenance.LLM_ASSISTED,
        Provenance.NONE,
    }


@pytest.mark.skipif(not _has_book(), reason="real book file not present at test/")
def test_extract_each_detected_chapter(tmp_cache_dir: Path) -> None:
    s = survey(BOOK, cache_dir=tmp_cache_dir)
    if not s.chapters:
        pytest.skip(f"no chapters detected (map.provenance={s.map.provenance.value})")

    for chapter in s.chapters:
        c = extract_chapter(BOOK, chapter.index, cache_dir=tmp_cache_dir)
        assert c.chapter.index == chapter.index
        assert isinstance(chapter.locator, PageRange)
        assert min(c.quality.pages_processed) >= chapter.locator.start_page
        assert max(c.quality.pages_processed) <= chapter.locator.end_page
        non_break = [b for b in c.simple_view if b.type != "page_break"]
        assert non_break, f"chapter {chapter.index} produced no content blocks"
        for grade_field in ("docling_mean_grade", "docling_low_grade"):
            v = getattr(s.quality, grade_field)
            assert v is None or isinstance(v, Confidence)
