"""Tests for the chapter-map builder."""
from __future__ import annotations

from book_ingestion.ir import Confidence, PageRange, Provenance
from book_ingestion.structure.embedded_toc import HeadingHint, build_chapter_map


def test_no_headings_returns_empty_map() -> None:
    chapters, info = build_chapter_map([], total_pages=100)
    assert chapters == []
    assert info.provenance == Provenance.NONE
    assert info.confidence == Confidence.POOR
    assert info.method == "none"


def test_top_level_headings_become_chapters() -> None:
    hints = [
        HeadingHint(text="Chapter 1 — Introduction", level=1, page=1),
        HeadingHint(text="Chapter 2 — Methods", level=1, page=20),
        HeadingHint(text="Chapter 3 — Results", level=1, page=50),
    ]
    chapters, info = build_chapter_map(hints, total_pages=100)
    assert [c.title for c in chapters] == [
        "Chapter 1 — Introduction",
        "Chapter 2 — Methods",
        "Chapter 3 — Results",
    ]
    assert isinstance(chapters[0].locator, PageRange)
    assert chapters[0].locator.start_page == 1
    assert chapters[0].locator.end_page == 19
    assert chapters[1].locator.end_page == 49  # type: ignore[union-attr]
    assert chapters[2].locator.end_page == 100  # type: ignore[union-attr]
    assert info.provenance == Provenance.EMBEDDED
    assert info.method == "pdf_outline"


def test_sub_headings_are_ignored_at_chapter_level() -> None:
    hints = [
        HeadingHint(text="Chapter 1", level=1, page=1),
        HeadingHint(text="1.1 Sub", level=2, page=5),
        HeadingHint(text="Chapter 2", level=1, page=10),
    ]
    chapters, _ = build_chapter_map(hints, total_pages=20)
    assert len(chapters) == 2
    assert chapters[0].locator.end_page == 9  # type: ignore[union-attr]


def test_single_chapter_runs_to_last_page() -> None:
    hints = [HeadingHint(text="Sole Chapter", level=1, page=1)]
    chapters, _ = build_chapter_map(hints, total_pages=10)
    assert chapters[0].locator.end_page == 10  # type: ignore[union-attr]


def test_chapter_indices_are_zero_based_and_dense() -> None:
    hints = [
        HeadingHint(text="A", level=1, page=1),
        HeadingHint(text="B", level=1, page=5),
        HeadingHint(text="C", level=1, page=9),
    ]
    chapters, _ = build_chapter_map(hints, total_pages=12)
    assert [c.index for c in chapters] == [0, 1, 2]


def test_returns_inferred_when_caller_says_so() -> None:
    hints = [HeadingHint(text="A", level=1, page=1)]
    _, info = build_chapter_map(hints, total_pages=10, provenance=Provenance.INFERRED, method="typographic")
    assert info.provenance == Provenance.INFERRED
    assert info.method == "typographic"


def test_inverted_range_clamps_to_single_page() -> None:
    """Consecutive level-1 hints on the same (or earlier) page must still
    yield a valid PageRange where end_page >= start_page."""
    hints = [
        HeadingHint(text="Chapter One Cover", level=1, page=14),
        HeadingHint(text="Chapter One Heading", level=1, page=14),
        HeadingHint(text="Chapter Two", level=1, page=33),
    ]
    chapters, _ = build_chapter_map(hints, total_pages=100)
    # All three chapters retained
    assert [c.title for c in chapters] == [
        "Chapter One Cover",
        "Chapter One Heading",
        "Chapter Two",
    ]
    # The clamped chapter has a 1-page range, not an inverted one.
    assert isinstance(chapters[0].locator, PageRange)
    assert chapters[0].locator.start_page == 14
    assert chapters[0].locator.end_page == 14
    assert chapters[0].locator.end_page >= chapters[0].locator.start_page
    assert chapters[1].locator.start_page == 14  # type: ignore[union-attr]
    assert chapters[1].locator.end_page == 32  # type: ignore[union-attr]  # one before next
