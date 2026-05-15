"""Backend integration tests for EpubNativeBackend.extract_chapter()."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion.backends.base import Context
from book_ingestion.backends.epub_native import EpubNativeBackend
from book_ingestion.cache import Cache
from book_ingestion.ir import Heading, Paragraph
from tests.fixtures.epub import (
    build_epub_with_chapters,
    build_epub_with_inline_page_anchors,
    build_epub_with_malformed_xhtml,
)


@pytest.fixture
def backend() -> EpubNativeBackend:
    return EpubNativeBackend()


@pytest.fixture
def ctx(tmp_cache_dir: Path) -> Context:
    return Context(cache=Cache(root=tmp_cache_dir), use_cache=True)


def test_extract_single_file_chapter(backend: EpubNativeBackend, ctx: Context, tmp_path: Path) -> None:
    p = build_epub_with_chapters(
        tmp_path / "x.epub",
        chapters=[
            {"id": "c1", "href": "ch1.xhtml", "title": "Chapter One",
             "body_xhtml": "<h1>Chapter One</h1><p>First para.</p><p>Second para.</p>"},
            {"id": "c2", "href": "ch2.xhtml", "title": "Chapter Two",
             "body_xhtml": "<h1>Chapter Two</h1><p>Third para.</p>"},
        ],
    )
    c = backend.extract_chapter(p, 0, ctx=ctx)
    assert c.kind == "chapter_content"
    assert c.chapter.title == "Chapter One"
    headings = [b for b in c.simple_view if isinstance(b, Heading)]
    paras = [b for b in c.simple_view if isinstance(b, Paragraph)]
    assert headings[0].text == "Chapter One"
    assert {pp.text for pp in paras} == {"First para.", "Second para."}
    # Crucially: no blocks from chapter 2
    assert "Third para." not in {pp.text for pp in paras}


def test_extract_index_out_of_range(backend: EpubNativeBackend, ctx: Context, tmp_path: Path) -> None:
    p = build_epub_with_chapters(tmp_path / "small.epub")
    with pytest.raises(IndexError):
        backend.extract_chapter(p, 99, ctx=ctx)


def test_extract_xhtml_parse_failure_emits_failed_region(
    backend: EpubNativeBackend, ctx: Context, tmp_path: Path
) -> None:
    p = build_epub_with_malformed_xhtml(tmp_path / "broken.epub")
    c = backend.extract_chapter(p, 0, ctx=ctx)
    assert any(b.type == "failed_region" for b in c.simple_view)
    assert "xhtml_parse_failure" in c.quality.flags


def test_extract_with_inline_page_anchors_stamps_page_label(
    backend: EpubNativeBackend, ctx: Context, tmp_path: Path
) -> None:
    p = build_epub_with_inline_page_anchors(tmp_path / "anchors.epub")
    c = backend.extract_chapter(p, 0, ctx=ctx)
    paras = [b for b in c.simple_view if isinstance(b, Paragraph)]
    labels = {pp.page_label for pp in paras}
    # The fixture has page-7, page-8, page-9 — at least one para should be stamped
    assert any(lbl in {"7", "8", "9"} for lbl in labels)


def test_extract_cache_hit(backend: EpubNativeBackend, ctx: Context, tmp_path: Path) -> None:
    p = build_epub_with_chapters(tmp_path / "cached.epub")
    c1 = backend.extract_chapter(p, 0, ctx=ctx)
    c2 = backend.extract_chapter(p, 0, ctx=ctx)
    assert c1.model_dump(mode="json") == c2.model_dump(mode="json")


def test_extract_multi_file_chapter_inserts_page_breaks(
    backend: EpubNativeBackend, ctx: Context, tmp_path: Path
) -> None:
    """One chapter spanning 2 spine items should yield blocks from both,
    separated by a PageBreak."""
    p = build_epub_with_chapters(
        tmp_path / "multi.epub",
        chapters=[
            {"id": "p1", "href": "p1.xhtml", "title": "Page 1",
             "body_xhtml": "<p>First file body.</p>"},
            {"id": "p2", "href": "p2.xhtml", "title": "Page 2",
             "body_xhtml": "<p>Second file body.</p>"},
            {"id": "p3", "href": "p3.xhtml", "title": "Part 2",
             "body_xhtml": "<p>Part two starts here.</p>"},
        ],
        nav_entries=[
            {"title": "Part 1", "target_href": "p1.xhtml", "target_frag": None},
            {"title": "Part 2", "target_href": "p3.xhtml", "target_frag": None},
        ],
    )
    c = backend.extract_chapter(p, 0, ctx=ctx)
    paras = [b for b in c.simple_view if isinstance(b, Paragraph)]
    assert {pp.text for pp in paras} == {"First file body.", "Second file body."}
    page_breaks = [b for b in c.simple_view if b.type == "page_break"]
    assert len(page_breaks) >= 1


def test_extract_fragment_bounded_chapter(
    backend: EpubNativeBackend, ctx: Context, tmp_path: Path
) -> None:
    """nav targets fragments inside a single spine file: chapter A bounded by chapB."""
    from tests.fixtures.epub import build_epub_with_chapter_spanning_file
    p = build_epub_with_chapter_spanning_file(tmp_path / "span.epub")
    c_a = backend.extract_chapter(p, 0, ctx=ctx)
    c_b = backend.extract_chapter(p, 1, ctx=ctx)
    a_texts = {getattr(b, "text", "") for b in c_a.simple_view}
    b_texts = {getattr(b, "text", "") for b in c_b.simple_view}
    assert "Body of chapter A." in a_texts
    assert "Body of chapter B." not in a_texts
    assert "Body of chapter B." in b_texts
    assert "Body of chapter A." not in b_texts
