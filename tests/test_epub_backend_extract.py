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
