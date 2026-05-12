"""Project a stream of Docling items into a simple_view block list.

The PDF backend (`backends/pdf_docling.py`) walks the real `DoclingDocument`
via `iterate_items()` and adapts each Docling item into the small `DoclingItem`
dataclass below. This separation keeps the projection logic unit-testable
without spinning up the full engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from book_ingestion.ir import (
    Block,
    Confidence,
    FailedRegion,
    FigureCaption,
    Footnote,
    Heading,
    PageBreak,
    Paragraph,
    Table,
)
from book_ingestion.quality.scoring import grade_from_score

ItemKind = Literal[
    "heading",
    "paragraph",
    "list_item",
    "table",
    "figure_caption",
    "footnote",
]


@dataclass(frozen=True)
class DoclingItem:
    """Adapter type bridging the real DoclingDocument items and our projection.

    `extra` carries kind-specific fields:
      - heading:        {"level": int}
      - paragraph:      {"footnote_ref": str | None, "list_marker": str | None}
      - table:          {"rows": list[list[str]] | None, "raw_text": str}
      - footnote:       {"fn_id": str}
    """
    kind: ItemKind
    text: str
    page: int
    score: float
    extra: dict[str, Any] = field(default_factory=dict)


_LOW_CONFIDENCE = Confidence.FAIR  # < FAIR → failed_region
_FAILED_REGION_THRESHOLD = {Confidence.POOR}


def project_to_simple_view(items: list[DoclingItem]) -> list[Block]:
    """Convert items to a list of simple_view blocks, inserting page_breaks
    between blocks that cross a page boundary."""
    blocks: list[Block] = []
    last_page: int | None = None

    for item in items:
        if last_page is not None and item.page != last_page:
            blocks.append(PageBreak(page=item.page))
        last_page = item.page
        blocks.append(_project_one(item))

    return blocks


def _project_one(item: DoclingItem) -> Block:
    grade = grade_from_score(item.score)

    if item.kind in ("paragraph", "list_item") and grade in _FAILED_REGION_THRESHOLD:
        return FailedRegion(page=item.page, reason="low_confidence_extraction", raw_text=item.text)

    if item.kind == "heading":
        level = int(item.extra.get("level", 1))
        return Heading(text=item.text, level=level, page=item.page, confidence=grade)

    if item.kind in ("paragraph", "list_item"):
        ref = item.extra.get("footnote_ref")
        return Paragraph(
            text=item.text,
            page=item.page,
            confidence=grade,
            footnote_refs=[ref] if ref else [],
            list_marker=item.extra.get("list_marker"),
        )

    if item.kind == "table":
        rows = item.extra.get("rows")
        raw_text = item.extra.get("raw_text", "")
        if grade in (Confidence.GOOD, Confidence.EXCELLENT) and rows:
            return Table(page=item.page, confidence=grade, rows=rows, raw_text=raw_text)
        return Table(page=item.page, confidence=grade, rows=None, raw_text=raw_text)

    if item.kind == "figure_caption":
        return FigureCaption(text=item.text, page=item.page, confidence=grade)

    if item.kind == "footnote":
        fn_id = str(item.extra.get("fn_id", "fn-?"))
        return Footnote(id=fn_id, text=item.text, page=item.page, confidence=grade)

    return FailedRegion(page=item.page, reason="unknown_item_type", raw_text=item.text)
