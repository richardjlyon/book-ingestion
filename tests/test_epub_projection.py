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
