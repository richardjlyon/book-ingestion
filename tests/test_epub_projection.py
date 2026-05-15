"""Tests for project_xhtml_to_blocks — XHTML element → simple_view block."""
from __future__ import annotations

import pytest

from book_ingestion.ir import (
    Confidence,
    FigureCaption,
    Footnote,
    Heading,
    Paragraph,
    Table,
)
from book_ingestion.projection.epub_to_simple_view import project_xhtml_to_blocks


def _wrap(body: str) -> bytes:
    """Wrap body XHTML in a minimal valid document."""
    return (
        '<?xml version="1.0"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">'
        f'<body>{body}</body></html>'
    ).encode()


def test_paragraph_is_emitted_as_paragraph_block() -> None:
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap("<p>Hello world.</p>"),
        spine_idx=1, page_label_map={},
    )
    assert len(blocks) == 1
    assert isinstance(blocks[0], Paragraph)
    assert blocks[0].text == "Hello world."
    assert blocks[0].page == 1
    assert blocks[0].page_label is None
    assert blocks[0].confidence == Confidence.EXCELLENT


@pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
def test_heading_levels_round_trip(level: int) -> None:
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap(f"<h{level}>Heading {level}</h{level}>"),
        spine_idx=1, page_label_map={},
    )
    assert len(blocks) == 1
    assert isinstance(blocks[0], Heading)
    assert blocks[0].level == level
    assert blocks[0].text == f"Heading {level}"


def test_blockquote_is_normalised_to_paragraph() -> None:
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap("<blockquote><p>Cited prose.</p></blockquote>"),
        spine_idx=1, page_label_map={},
    )
    # Per spec §3.3: blockquote → Paragraph (no enum extension)
    assert all(isinstance(b, Paragraph) for b in blocks)
    assert any(b.text == "Cited prose." for b in blocks)


def test_table_emits_table_block() -> None:
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap(
            "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>"
        ),
        spine_idx=1, page_label_map={},
    )
    table_blocks = [b for b in blocks if isinstance(b, Table)]
    assert len(table_blocks) == 1
    assert table_blocks[0].rows == [["A", "B"], ["C", "D"]]


def test_aside_footnote_emits_footnote_block() -> None:
    body = '<aside epub:type="footnote" id="fn1"><p>Footnote text.</p></aside>'
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap(body), spine_idx=1, page_label_map={},
    )
    fns = [b for b in blocks if isinstance(b, Footnote)]
    assert len(fns) == 1
    assert fns[0].id == "fn1"
    assert "Footnote text." in fns[0].text


def test_figcaption_emits_figure_caption() -> None:
    body = '<figure><img src="x.jpg"/><figcaption>Cap</figcaption></figure>'
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap(body), spine_idx=1, page_label_map={},
    )
    caps = [b for b in blocks if isinstance(b, FigureCaption)]
    assert len(caps) == 1
    assert caps[0].text == "Cap"


def test_heading_then_paragraph_in_order() -> None:
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap("<h1>Title</h1><p>Body.</p>"),
        spine_idx=1, page_label_map={},
    )
    assert len(blocks) == 2
    assert isinstance(blocks[0], Heading)
    assert isinstance(blocks[1], Paragraph)


def test_xhtml_parse_failure_emits_failed_region() -> None:
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=b"<html><body><p>Unclosed paragraph",
        spine_idx=2, page_label_map={},
    )
    assert len(blocks) == 1
    assert blocks[0].type == "failed_region"
    assert blocks[0].reason == "xhtml_parse_failure"
    assert blocks[0].page == 2
    # Salvage should preserve some text content (best-effort).
    assert blocks[0].raw_text is not None
    assert "Unclosed paragraph" in blocks[0].raw_text


def test_aside_footnote_does_not_double_emit_inner_paragraph() -> None:
    """The <p> inside an aside-footnote must NOT be emitted as a separate Paragraph."""
    body = '<aside epub:type="footnote" id="fn1"><p>Footnote text.</p></aside>'
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap(body), spine_idx=1, page_label_map={},
    )
    assert len(blocks) == 1
    assert blocks[0].type == "footnote"
    assert blocks[0].id == "fn1"
    assert "Footnote text." in blocks[0].text


def test_table_with_nested_table_does_not_duplicate_rows() -> None:
    """An inner <table> inside an outer <table>'s cell must not pollute the outer table's rows."""
    body = (
        '<table>'
        '<tr><td>outer A</td></tr>'
        '<tr><td><table><tr><td>inner</td></tr></table></td></tr>'
        '</table>'
    )
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap(body), spine_idx=1, page_label_map={},
    )
    tables = [b for b in blocks if b.type == "table"]
    # Only the outer table should be emitted (inner is absorbed via consumed_subtree).
    assert len(tables) == 1
    # Outer table should have exactly 2 rows.
    assert tables[0].rows is not None
    assert len(tables[0].rows) == 2


def test_page_anchors_update_page_label_and_are_not_emitted() -> None:
    body = (
        '<a class="page" id="page-7"/>'
        '<p>On page 7.</p>'
        '<a class="page" id="page-8"/>'
        '<p>On page 8.</p>'
    )
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap(body), spine_idx=1,
        page_label_map={"page-7": "7", "page-8": "8"},
    )
    paras = [b for b in blocks if isinstance(b, Paragraph)]
    assert len(paras) == 2
    assert paras[0].text == "On page 7."
    assert paras[0].page_label == "7"
    assert paras[1].text == "On page 8."
    assert paras[1].page_label == "8"


def test_boilerplate_nav_block_is_skipped() -> None:
    body = (
        '<nav epub:type="toc"><ol><li><a href="x">x</a></li></ol></nav>'
        '<p>Real content.</p>'
    )
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap(body), spine_idx=1, page_label_map={},
    )
    paras = [b for b in blocks if isinstance(b, Paragraph)]
    assert len(paras) == 1
    assert paras[0].text == "Real content."


def test_cover_titlepage_div_is_skipped() -> None:
    body = (
        '<div epub:type="cover"><p>Cover image.</p></div>'
        '<p>Real content.</p>'
    )
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap(body), spine_idx=1, page_label_map={},
    )
    paras = [b for b in blocks if isinstance(b, Paragraph)]
    assert len(paras) == 1
    assert paras[0].text == "Real content."


def test_fragment_bounded_slice() -> None:
    body = (
        '<h1 id="chapA">A</h1><p>Body of A.</p>'
        '<h1 id="chapB">B</h1><p>Body of B.</p>'
    )
    blocks_a = project_xhtml_to_blocks(
        xhtml_bytes=_wrap(body), spine_idx=1, page_label_map={},
        start_frag="chapA", end_frag="chapB",
    )
    texts = [getattr(b, "text", "") for b in blocks_a]
    assert "A" in texts
    assert "Body of A." in texts
    assert "B" not in texts
    assert "Body of B." not in texts


def test_pagebreak_span_uses_title_attribute() -> None:
    """`<span epub:type="pagebreak" id="x" title="42"/>` updates page_label to '42'."""
    body = (
        '<p>Before.</p>'
        '<span epub:type="pagebreak" id="pb1" title="42"/>'
        '<p>After.</p>'
    )
    blocks = project_xhtml_to_blocks(
        xhtml_bytes=_wrap(body), spine_idx=1,
        page_label_map={"pb1": "42"},
    )
    paras = [b for b in blocks if isinstance(b, Paragraph)]
    assert len(paras) == 2
    assert paras[0].page_label is None  # before the pagebreak
    assert paras[1].page_label == "42"
