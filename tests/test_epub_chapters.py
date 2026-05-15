"""Tests for build_chapter_map_epub — chapter reconciliation recipe."""
from __future__ import annotations

from pathlib import Path

from book_ingestion.extractors._epub_common import (
    find_opf_path,
    open_epub_zip,
    parse_opf_root,
)
from book_ingestion.ir import Confidence, Provenance, SpineRange
from book_ingestion.structure.epub_chapters import (
    build_chapter_map_epub,
    extract_spine,
)
from tests.fixtures.epub import build_epub_with_chapters


def test_extract_spine_returns_items_in_order(tmp_path: Path) -> None:
    p = build_epub_with_chapters(
        tmp_path / "x.epub",
        chapters=[
            {"id": "c1", "href": "ch1.xhtml", "title": "Ch1", "body_xhtml": "<p>a</p>"},
            {"id": "c2", "href": "ch2.xhtml", "title": "Ch2", "body_xhtml": "<p>b</p>"},
        ],
    )
    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        spine = extract_spine(opf_root, opf_dir="OEBPS")
    assert [s.href for s in spine] == ["OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml"]
    assert all(s.media_type == "application/xhtml+xml" for s in spine)


def test_spine_only_path_emits_one_chapter_per_item(tmp_path: Path) -> None:
    """When nav is None → spine-only fallback (Step 4)."""
    p = build_epub_with_chapters(
        tmp_path / "x.epub",
        chapters=[
            {"id": "c1", "href": "ch1.xhtml", "title": "Ch1",
             "body_xhtml": "<h1>Real Title 1</h1><p>a</p>"},
            {"id": "c2", "href": "ch2.xhtml", "title": "Ch2",
             "body_xhtml": "<h1>Real Title 2</h1><p>b</p>"},
        ],
    )
    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        spine = extract_spine(opf_root, opf_dir="OEBPS")
        chapters, map_info, flags = build_chapter_map_epub(
            spine=spine, nav=None, zf=zf, opf_dir="OEBPS",
        )
    assert len(chapters) == 2
    assert chapters[0].title == "Real Title 1"
    assert chapters[1].title == "Real Title 2"
    assert all(c.provenance == Provenance.INFERRED for c in chapters)
    assert all(c.confidence == Confidence.FAIR for c in chapters)
    assert chapters[0].locator == SpineRange(start_spine=1, end_spine=1)
    assert chapters[1].locator == SpineRange(start_spine=2, end_spine=2)
    assert map_info.method == "epub_spine"
    assert "spine_only" in flags


def test_spine_only_path_falls_back_to_filename_when_no_h1(tmp_path: Path) -> None:
    p = build_epub_with_chapters(
        tmp_path / "x.epub",
        chapters=[
            {"id": "c1", "href": "03_chapter_one.xhtml", "title": "Ignored",
             "body_xhtml": "<p>no headings here</p>"},
        ],
    )
    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        spine = extract_spine(opf_root, opf_dir="OEBPS")
        chapters, _, _ = build_chapter_map_epub(
            spine=spine, nav=None, zf=zf, opf_dir="OEBPS",
        )
    assert chapters[0].title == "Chapter One"  # humanised from "03_chapter_one"
