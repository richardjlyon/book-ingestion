"""Tests for build_chapter_map_epub — chapter reconciliation recipe."""
from __future__ import annotations

import zipfile
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


def _parse_nav_from_epub(zf: zipfile.ZipFile, opf_dir: str):
    """Test helper — return parsed top-level nav entries."""
    from book_ingestion.structure.epub_chapters import parse_nav_or_ncx
    return parse_nav_or_ncx(zf, opf_dir=opf_dir)


def test_nav_driven_clean_one_file_per_chapter(tmp_path: Path) -> None:
    p = build_epub_with_chapters(
        tmp_path / "x.epub",
        chapters=[
            {"id": "c1", "href": "ch1.xhtml", "title": "Chapter One",
             "body_xhtml": "<p>a</p>"},
            {"id": "c2", "href": "ch2.xhtml", "title": "Chapter Two",
             "body_xhtml": "<p>b</p>"},
        ],
    )
    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        spine = extract_spine(opf_root, opf_dir="OEBPS")
        nav = _parse_nav_from_epub(zf, opf_dir="OEBPS")
        chapters, map_info, flags = build_chapter_map_epub(
            spine=spine, nav=nav, zf=zf, opf_dir="OEBPS",
        )
    assert len(chapters) == 2
    assert chapters[0].title == "Chapter One"
    assert chapters[0].locator == SpineRange(start_spine=1, end_spine=1)
    assert chapters[1].locator == SpineRange(start_spine=2, end_spine=2)
    assert all(c.provenance == Provenance.EMBEDDED for c in chapters)
    assert all(c.confidence == Confidence.EXCELLENT for c in chapters)
    assert map_info.method == "epub_nav"
    assert "nav_used" in flags
    assert "chapter_spans_multiple_files" not in flags
    assert "headings_split_used" not in flags


def test_nav_driven_multi_file_chapter(tmp_path: Path) -> None:
    """One nav entry pointing at the first of N spine files → SpineRange spans them."""
    p = build_epub_with_chapters(
        tmp_path / "x.epub",
        chapters=[
            {"id": "p1", "href": "p1.xhtml", "title": "Part 1 page 1", "body_xhtml": "<p>a</p>"},
            {"id": "p2", "href": "p2.xhtml", "title": "Part 1 page 2", "body_xhtml": "<p>b</p>"},
            {"id": "p3", "href": "p3.xhtml", "title": "Part 2", "body_xhtml": "<p>c</p>"},
        ],
        nav_entries=[
            {"title": "Part 1", "target_href": "p1.xhtml", "target_frag": None},
            {"title": "Part 2", "target_href": "p3.xhtml", "target_frag": None},
        ],
    )
    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        spine = extract_spine(opf_root, opf_dir="OEBPS")
        nav = _parse_nav_from_epub(zf, opf_dir="OEBPS")
        chapters, _, flags = build_chapter_map_epub(
            spine=spine, nav=nav, zf=zf, opf_dir="OEBPS",
        )
    assert len(chapters) == 2
    assert chapters[0].locator == SpineRange(start_spine=1, end_spine=2)
    assert chapters[1].locator == SpineRange(start_spine=3, end_spine=3)
    assert "chapter_spans_multiple_files" in flags


def test_nav_driven_chapter_starts_mid_file(tmp_path: Path) -> None:
    """Two nav entries with fragments inside the same spine file → fragment-bounded."""
    from tests.fixtures.epub import build_epub_with_chapter_spanning_file
    p = build_epub_with_chapter_spanning_file(tmp_path / "span.epub")
    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        spine = extract_spine(opf_root, opf_dir="OEBPS")
        nav = _parse_nav_from_epub(zf, opf_dir="OEBPS")
        chapters, _, flags = build_chapter_map_epub(
            spine=spine, nav=nav, zf=zf, opf_dir="OEBPS",
        )
    assert len(chapters) == 2
    assert chapters[0].locator.start_spine == 1
    assert chapters[0].locator.start_frag == "chapA"
    assert chapters[1].locator.start_frag == "chapB"
    assert "headings_split_used" in flags


def test_headings_only_when_spine_empty(tmp_path: Path) -> None:
    """When spine is empty (e.g. all items dropped by content-XHTML filter),
    fall back to walking manifest content files for <h1> headings."""
    files = {
        "mimetype": "application/epub+zip",
        "META-INF/container.xml": (
            '<?xml version="1.0"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>'
            '</container>'
        ),
        "OEBPS/content.opf": (
            '<?xml version="1.0"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:title>X</dc:title><dc:identifier>1</dc:identifier><dc:language>en</dc:language>'
            '</metadata>'
            '<manifest>'
            '  <item id="img" href="cover.jpg" media-type="image/jpeg"/>'
            '  <item id="ch" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest>'
            '<spine><itemref idref="img"/></spine>'
            '</package>'
        ),
        "OEBPS/cover.jpg": "fake jpeg bytes",
        "OEBPS/ch1.xhtml": (
            '<?xml version="1.0"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
            '<h1>First Chapter</h1><p>a</p>'
            '<h1>Second Chapter</h1><p>b</p>'
            '</body></html>'
        ),
    }
    p = tmp_path / "headings.epub"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf_out:
        for name, content in files.items():
            zf_out.writestr(name, content)

    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        spine = extract_spine(opf_root, opf_dir="OEBPS")
        assert spine == []  # spine has only the image; filter drops it
        chapters, map_info, flags = build_chapter_map_epub(
            spine=spine, nav=None, zf=zf, opf_dir="OEBPS", opf_root=opf_root,
        )
    assert len(chapters) == 2
    assert chapters[0].title == "First Chapter"
    assert chapters[1].title == "Second Chapter"
    assert map_info.method == "epub_headings"
    assert map_info.provenance == Provenance.INFERRED
    assert "toc_unresolved" in flags


def test_dispatcher_empty_spine_no_opf_root_returns_empty(tmp_path: Path) -> None:
    """Backward-compat: existing callers that don't pass opf_root still get the
    no-chapters return when spine is empty."""
    p = build_epub_with_chapters(tmp_path / "x.epub")
    with open_epub_zip(p) as zf:
        chapters, map_info, flags = build_chapter_map_epub(
            spine=[], nav=None, zf=zf, opf_dir="OEBPS",
        )
    assert chapters == []
    assert map_info.provenance == Provenance.NONE
    assert map_info.method == "none"
    assert "toc_unresolved" in flags


def test_dispatcher_empty_nav_routes_to_spine_only(tmp_path: Path) -> None:
    """nav=[] (empty list, distinct from None) should route to spine-only fallback."""
    p = build_epub_with_chapters(
        tmp_path / "x.epub",
        chapters=[
            {"id": "c1", "href": "ch1.xhtml", "title": "Ch1",
             "body_xhtml": "<h1>One</h1>"},
            {"id": "c2", "href": "ch2.xhtml", "title": "Ch2",
             "body_xhtml": "<h1>Two</h1>"},
        ],
    )
    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        spine = extract_spine(opf_root, opf_dir="OEBPS")
        chapters, map_info, flags = build_chapter_map_epub(
            spine=spine, nav=[], zf=zf, opf_dir="OEBPS",
        )
    assert len(chapters) == 2
    assert map_info.method == "epub_spine"
    assert "spine_only" in flags


def test_extract_spine_filters_non_content_media_types(tmp_path: Path) -> None:
    """An itemref pointing at a non-content-XHTML manifest item is dropped."""
    files = {
        "mimetype": "application/epub+zip",
        "META-INF/container.xml": (
            '<?xml version="1.0"?>'
            '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>'
            '</container>'
        ),
        "OEBPS/content.opf": (
            '<?xml version="1.0"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:title>X</dc:title><dc:identifier>1</dc:identifier><dc:language>en</dc:language>'
            '</metadata>'
            '<manifest>'
            '  <item id="img" href="cover.jpg" media-type="image/jpeg"/>'
            '  <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
            '  <item id="ch" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest>'
            '<spine>'
            '  <itemref idref="img"/>'
            '  <itemref idref="ncx"/>'
            '  <itemref idref="ch"/>'
            '</spine>'
            '</package>'
        ),
        "OEBPS/cover.jpg": "fake",
        "OEBPS/toc.ncx": "<ncx/>",
        "OEBPS/ch1.xhtml": (
            '<?xml version="1.0"?>'
            '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>x</p></body></html>'
        ),
    }
    p = tmp_path / "filter.epub"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf_out:
        for name, content in files.items():
            zf_out.writestr(name, content)
    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        spine = extract_spine(opf_root, opf_dir="OEBPS")
    # Only ch1.xhtml survives the content-XHTML filter
    assert len(spine) == 1
    assert spine[0].href == "OEBPS/ch1.xhtml"
    assert spine[0].idx == 1


def test_parse_nav_or_ncx_falls_back_to_ncx_for_epub2(tmp_path: Path) -> None:
    """epub3=False produces an EPUB 2 fixture with toc.ncx instead of nav.xhtml."""
    p = build_epub_with_chapters(
        tmp_path / "epub2.epub",
        chapters=[
            {"id": "c1", "href": "ch1.xhtml", "title": "First", "body_xhtml": "<p>a</p>"},
            {"id": "c2", "href": "ch2.xhtml", "title": "Second", "body_xhtml": "<p>b</p>"},
        ],
        epub3=False,
    )
    with open_epub_zip(p) as zf:
        from book_ingestion.structure.epub_chapters import parse_nav_or_ncx
        nav = parse_nav_or_ncx(zf, opf_dir="OEBPS")
    assert nav is not None
    assert len(nav) == 2
    assert nav[0].title == "First"
    assert nav[0].target_href == "ch1.xhtml"
    assert nav[1].target_href == "ch2.xhtml"
