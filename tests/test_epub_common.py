"""Tests for shared EPUB zip/OPF/DRM/pageList helpers."""
from __future__ import annotations

from pathlib import Path

from book_ingestion.extractors._epub_common import (
    detect_drm,
    find_opf_path,
    open_epub_zip,
    parse_opf_root,
    read_pageList_anchors,
)
from tests.fixtures.epub import (
    build_epub,
    build_epub_with_chapters,
    build_epub_with_drm,
    build_epub_with_inline_page_anchors,
    build_malformed_epub,
)


def test_find_opf_path_returns_oebps_content_opf(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "x.epub",
        dc_title="X", creators=[], isbn=None, publisher=None, language="en",
    )
    with open_epub_zip(p) as zf:
        assert find_opf_path(zf) == "OEBPS/content.opf"


def test_find_opf_path_returns_none_when_container_missing(tmp_path: Path) -> None:
    p = build_malformed_epub(tmp_path / "broken.epub")
    with open_epub_zip(p) as zf:
        assert find_opf_path(zf) is None


def test_detect_drm_adobe(tmp_path: Path) -> None:
    p = build_epub_with_drm(tmp_path / "drm.epub")
    with open_epub_zip(p) as zf:
        assert detect_drm(zf) is True


def test_detect_drm_clean_epub(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "clean.epub",
        dc_title="X", creators=[], isbn=None, publisher=None, language="en",
    )
    with open_epub_zip(p) as zf:
        assert detect_drm(zf) is False


def test_read_pageList_anchors_inline(tmp_path: Path) -> None:
    """In-content `<a class="page" id="page-N"/>` anchors are surfaced."""
    p = build_epub_with_inline_page_anchors(tmp_path / "anchors.epub")
    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        anchors = read_pageList_anchors(opf_root, zf, set(zf.namelist()), opf_dir="OEBPS")
    # Expect anchors mapping printed-page label → href fragment (or anchor id).
    # The fixture has page-7, page-8, page-9.
    assert "7" in anchors.values()
    assert "8" in anchors.values()
    assert "9" in anchors.values()


def test_read_pageList_anchors_nav_pageList(tmp_path: Path) -> None:
    """EPUB 3 `<nav epub:type="page-list">` entries are surfaced."""
    p = build_epub_with_chapters(
        tmp_path / "pl.epub",
        chapters=[
            {"id": "c1", "href": "ch1.xhtml", "title": "Ch1",
             "body_xhtml": "<p>body</p>"},
        ],
        page_list=[("12", "ch1.xhtml#p12"), ("13", "ch1.xhtml#p13")],
    )
    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        anchors = read_pageList_anchors(opf_root, zf, set(zf.namelist()), opf_dir="OEBPS")
    assert "12" in anchors.values()
    assert "13" in anchors.values()


def test_read_pageList_anchors_absent(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "x.epub",
        dc_title="X", creators=[], isbn=None, publisher=None, language="en",
    )
    with open_epub_zip(p) as zf:
        opf_path = find_opf_path(zf)
        assert opf_path is not None
        opf_root = parse_opf_root(zf, opf_path)
        assert opf_root is not None
        anchors = read_pageList_anchors(opf_root, zf, set(zf.namelist()), opf_dir="OEBPS")
    assert anchors == {}
