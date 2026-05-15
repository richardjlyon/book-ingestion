"""End-to-end acceptance tests against real EPUB fixtures.

These are the M2.1 acceptance gate. Skipped when fixture files are absent
(CI without binary fixtures still runs); pass fully in the dev environment
where the user has the EPUBs in `test/`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion import extract_chapter, survey
from book_ingestion.ir import Provenance, SpineRange

# Pappé — primary acceptance fixture (Calibre-converted, no pageList expected).
PAPPE_EPUB = (
    Path(__file__).parent.parent
    / "test"
    / "The Ethnic Cleansing of Palestine (Ilan Pappe) (z-library.sk, 1lib.sk, z-lib.sk).epub"
)

pytestmark = [pytest.mark.slow, pytest.mark.real_book]


def _has(p: Path) -> bool:
    return p.exists()


@pytest.mark.skipif(not _has(PAPPE_EPUB), reason="Pappé EPUB not present in test/")
def test_pappe_survey_returns_valid_book_survey(tmp_cache_dir: Path) -> None:
    s = survey(PAPPE_EPUB, cache_dir=tmp_cache_dir)
    assert s.kind == "book_survey"
    assert s.source.format == "epub"
    assert s.source.size_bytes > 100_000
    assert s.quality.backend == "epub_native"
    assert s.map.provenance in {Provenance.EMBEDDED, Provenance.INFERRED, Provenance.NONE}
    assert s.chapters, "expected at least one chapter from Pappé"
    # Every chapter has a SpineRange locator
    assert all(isinstance(c.locator, SpineRange) for c in s.chapters)


@pytest.mark.skipif(not _has(PAPPE_EPUB), reason="Pappé EPUB not present in test/")
def test_pappe_extract_chapter_returns_clean_content(tmp_cache_dir: Path) -> None:
    s = survey(PAPPE_EPUB, cache_dir=tmp_cache_dir)
    # Pick the middle chapter as a representative of "normal" content.
    mid = len(s.chapters) // 2
    c = extract_chapter(PAPPE_EPUB, mid, cache_dir=tmp_cache_dir)
    assert c.kind == "chapter_content"
    assert c.simple_view, "extracted chapter should have at least one block"
    failed = [b for b in c.simple_view if b.type == "failed_region"]
    assert not failed, f"clean Calibre EPUB should produce no failed_region: got {failed}"


@pytest.mark.skipif(not _has(PAPPE_EPUB), reason="Pappé EPUB not present in test/")
def test_pappe_all_chapters_extract_without_crash(tmp_cache_dir: Path) -> None:
    """Smoke test: extracting every chapter should never raise."""
    s = survey(PAPPE_EPUB, cache_dir=tmp_cache_dir)
    for i, _ in enumerate(s.chapters):
        c = extract_chapter(PAPPE_EPUB, i, cache_dir=tmp_cache_dir)
        assert c.simple_view is not None  # may be empty for cover/copyright spine items


SHLAIM_EPUB = (
    Path(__file__).parent.parent
    / "test"
    / "The Iron Wall Israel and the Arab World (Avi Shlaim) (z-library.sk, 1lib.sk, z-lib.sk).epub"
)


@pytest.mark.skipif(not _has(SHLAIM_EPUB), reason="Shlaim EPUB not present in test/")
def test_shlaim_survey_returns_valid_book_survey(tmp_cache_dir: Path) -> None:
    s = survey(SHLAIM_EPUB, cache_dir=tmp_cache_dir)
    assert s.source.format == "epub"
    assert s.chapters
    # If Shlaim carries a pageList, page_label_provenance must reflect it.
    if s.page_label_provenance == Provenance.EMBEDDED:
        assert "page_labels_embedded" in s.quality.flags


@pytest.mark.skipif(not _has(SHLAIM_EPUB), reason="Shlaim EPUB not present in test/")
def test_shlaim_extract_first_chapter(tmp_cache_dir: Path) -> None:
    # Chapter 0 is the Cover (image-only spine item — empty simple_view by design).
    # Use chapter 1 (Title page) as the first content chapter.
    c = extract_chapter(SHLAIM_EPUB, 1, cache_dir=tmp_cache_dir)
    assert c.simple_view
    failed = [b for b in c.simple_view if b.type == "failed_region"]
    assert not failed, f"clean Norton EPUB should produce no failed_region: got {failed}"
