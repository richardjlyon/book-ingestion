"""Tests for DoclingDocument → simple_view projection."""
from __future__ import annotations

from book_ingestion.ir import (
    Confidence,
    FailedRegion,
    FigureCaption,
    Footnote,
    Heading,
    PageBreak,
    Paragraph,
    Table,
)
from book_ingestion.projection.to_simple_view import (
    DoclingItem,
    ItemKind,
    project_to_simple_view,
)


def _item(kind: ItemKind, *, text: str = "", page: int, score: float = 0.95, **extra: object) -> DoclingItem:
    return DoclingItem(kind=kind, text=text, page=page, score=score, extra=dict(extra))


def test_paragraphs_and_headings_basic() -> None:
    items = [
        _item("heading", text="Chapter 3", page=10, level=1),
        _item("paragraph", text="First.", page=10),
        _item("paragraph", text="Second.", page=10),
    ]
    blocks = project_to_simple_view(items)
    assert blocks == [
        Heading(text="Chapter 3", level=1, page=10, confidence=Confidence.EXCELLENT),
        Paragraph(text="First.", page=10, confidence=Confidence.EXCELLENT),
        Paragraph(text="Second.", page=10, confidence=Confidence.EXCELLENT),
    ]


def test_page_break_inserted_between_pages() -> None:
    items = [
        _item("paragraph", text="On 10.", page=10),
        _item("paragraph", text="On 11.", page=11),
    ]
    blocks = project_to_simple_view(items)
    assert blocks[0] == Paragraph(text="On 10.", page=10, confidence=Confidence.EXCELLENT)
    assert blocks[1] == PageBreak(page=11)
    assert blocks[2] == Paragraph(text="On 11.", page=11, confidence=Confidence.EXCELLENT)


def test_table_kept_structured_when_good() -> None:
    items = [_item("table", page=20, score=0.92, rows=[["a", "b"], ["c", "d"]], raw_text="a b\nc d")]
    blocks = project_to_simple_view(items)
    assert blocks == [
        Table(page=20, confidence=Confidence.EXCELLENT, rows=[["a", "b"], ["c", "d"]], raw_text="a b\nc d"),
    ]


def test_table_falls_back_to_raw_text_when_uncertain() -> None:
    items = [_item("table", page=20, score=0.55, rows=[["a", "b"]], raw_text="a b")]
    blocks = project_to_simple_view(items)
    assert blocks == [
        Table(page=20, confidence=Confidence.FAIR, rows=None, raw_text="a b"),
    ]


def test_figure_caption() -> None:
    items = [_item("figure_caption", text="Figure 1.", page=15)]
    assert project_to_simple_view(items) == [
        FigureCaption(text="Figure 1.", page=15, confidence=Confidence.EXCELLENT)
    ]


def test_footnote_emitted_with_id() -> None:
    items = [
        _item("paragraph", text="A claim.", page=10, footnote_ref="fn-1"),
        _item("footnote", text="See ...", page=10, fn_id="fn-1"),
    ]
    blocks = project_to_simple_view(items)
    assert blocks[0] == Paragraph(
        text="A claim.", page=10, confidence=Confidence.EXCELLENT, footnote_refs=["fn-1"]
    )
    assert blocks[1] == Footnote(id="fn-1", text="See ...", page=10, confidence=Confidence.EXCELLENT)


def test_unknown_kind_becomes_failed_region() -> None:
    items = [_item("totally_unknown", text="???", page=5)]  # type: ignore[arg-type]
    blocks = project_to_simple_view(items)
    assert blocks == [
        FailedRegion(page=5, reason="unknown_item_type", raw_text="???"),
    ]


def test_poor_score_paragraph_becomes_failed_region() -> None:
    items = [_item("paragraph", text="garbled", page=8, score=0.10)]
    blocks = project_to_simple_view(items)
    assert blocks == [
        FailedRegion(page=8, reason="low_confidence_extraction", raw_text="garbled"),
    ]


def test_poor_score_list_item_becomes_failed_region() -> None:
    items = [_item("list_item", text="bullet", page=8, score=0.10)]
    blocks = project_to_simple_view(items)
    assert blocks == [
        FailedRegion(page=8, reason="low_confidence_extraction", raw_text="bullet"),
    ]


def test_page_labels_stamped_when_map_provided() -> None:
    items = [
        _item("paragraph", text="On 14.", page=14),
        _item("paragraph", text="On 15.", page=15),
    ]
    labels = {14: "10", 15: "11"}
    blocks = project_to_simple_view(items, page_labels=labels)
    assert blocks[0].page_label == "10"
    assert blocks[1].page_label == "11"  # the synthetic PageBreak between them
    assert blocks[2].page_label == "11"
