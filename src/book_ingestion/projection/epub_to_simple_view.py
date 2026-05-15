"""Project XHTML element trees into simple_view blocks.

See `docs/superpowers/specs/2026-05-14-m2.1-epub-ir-design.md` §6.

Page-anchor tracking, boilerplate filtering, and fragment-bounded slicing
land in Task 9. This module currently emits everything in document order
without those refinements.

Known deferrals (Task 9 + future):
- Page-anchor tracking, boilerplate filtering, and fragment-bounded slicing
  land in Task 9.
- <pre> blocks are not yet handled — spec §3.3 calls for them to become
  Paragraphs with verbatim content, but _text_of currently collapses whitespace.
  Opt-out logic for pre subtrees is a future enhancement; trade non-fiction
  (the M2.1 acceptance fixture genre) effectively never carries code blocks.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from book_ingestion.ir import (
    Block,
    Confidence,
    FailedRegion,
    FigureCaption,
    Footnote,
    Heading,
    Paragraph,
    Table,
)

_XHTML_NS = "http://www.w3.org/1999/xhtml"
_EPUB_NS = "http://www.idpf.org/2007/ops"
_HEADING_TAGS = {f"{{{_XHTML_NS}}}h{i}": i for i in range(1, 7)}


def _local(tag: str) -> str:
    """Strip namespace from a qualified tag name."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text_of(elem: ET.Element) -> str:
    """Concatenated text content of `elem` and descendants, whitespace-normalised."""
    parts = list(elem.itertext())
    joined = "".join(parts)
    return re.sub(r"\s+", " ", joined).strip()


def _table_rows(elem: ET.Element) -> list[list[str]]:
    """Extract a 2D string grid from a <table>.

    Only direct rows (under <table>, <thead>, <tbody>, <tfoot>) are collected;
    rows nested inside an inner <table> belong to that inner table, not this one.
    """
    rows: list[list[str]] = []

    def _collect_rows_from(container: ET.Element) -> None:
        for child in container:
            tag_local = _local(child.tag)
            if tag_local == "tr":
                cells: list[str] = []
                for c in child:
                    if _local(c.tag) in ("td", "th"):
                        cells.append(_text_of(c))
                if cells:
                    rows.append(cells)

    # Direct <tr> children of the <table>
    _collect_rows_from(elem)
    # And rows nested under thead / tbody / tfoot
    for section in elem:
        if _local(section.tag) in ("thead", "tbody", "tfoot"):
            _collect_rows_from(section)

    return rows


def project_xhtml_to_blocks(
    *,
    xhtml_bytes: bytes,
    spine_idx: int,
    page_label_map: dict[str, str],
    start_frag: str | None = None,
    end_frag: str | None = None,
) -> list[Block]:
    """Walk an XHTML document and emit a list of simple_view blocks.

    Parse failures emit a single `FailedRegion(reason="xhtml_parse_failure")`
    with best-effort raw-text salvage.

    `start_frag` / `end_frag` and page-anchor consumption land in Task 9.
    """
    try:
        root = ET.fromstring(xhtml_bytes)
    except ET.ParseError:
        try:
            text_only = re.sub(rb"<[^>]+>", b" ", xhtml_bytes).decode("utf-8", errors="replace")
            salvaged: str | None = re.sub(r"\s+", " ", text_only).strip() or None
        except Exception:
            salvaged = None
        return [FailedRegion(
            page=spine_idx, page_label=None,
            reason="xhtml_parse_failure", raw_text=salvaged,
        )]

    found_body = root.find(f"{{{_XHTML_NS}}}body")
    body = found_body if found_body is not None else root
    blocks: list[Block] = []
    current_page_label: str | None = None
    consumed_subtree: set[int] = set()  # id() of descendants whose container already emitted
    # start_frag / end_frag and page-anchor consumption land in Task 9.
    _ = start_frag
    _ = end_frag
    _ = page_label_map

    for elem in body.iter():
        if id(elem) in consumed_subtree:
            continue
        tag = elem.tag

        if tag in _HEADING_TAGS:
            text = _text_of(elem)
            if text:
                blocks.append(Heading(
                    text=text, level=_HEADING_TAGS[tag],
                    page=spine_idx, page_label=current_page_label,
                    confidence=Confidence.EXCELLENT,
                ))
        elif tag == f"{{{_XHTML_NS}}}p":
            text = _text_of(elem)
            if text:
                blocks.append(Paragraph(
                    text=text, page=spine_idx, page_label=current_page_label,
                    confidence=Confidence.EXCELLENT,
                ))
        elif tag == f"{{{_XHTML_NS}}}blockquote":
            inner_ps = list(elem.iter(f"{{{_XHTML_NS}}}p"))
            if not inner_ps:
                text = _text_of(elem)
                if text:
                    blocks.append(Paragraph(
                        text=text, page=spine_idx, page_label=current_page_label,
                        confidence=Confidence.EXCELLENT,
                    ))
            # If <p>s are nested, the outer body.iter() will visit them.
        elif tag == f"{{{_XHTML_NS}}}table":
            rows = _table_rows(elem)
            raw_text = "\n".join(" | ".join(r) for r in rows)
            blocks.append(Table(
                page=spine_idx, page_label=current_page_label,
                confidence=Confidence.EXCELLENT,
                rows=rows or None, raw_text=raw_text,
            ))
            # Suppress descendants — table cells are already absorbed via _text_of
            for d in elem.iter():
                if d is not elem:
                    consumed_subtree.add(id(d))
        elif tag == f"{{{_XHTML_NS}}}aside":
            epub_type = (elem.get(f"{{{_EPUB_NS}}}type") or "").strip()
            if epub_type == "footnote":
                fn_id = elem.get("id") or f"fn-{len(blocks)}"
                blocks.append(Footnote(
                    id=fn_id, text=_text_of(elem),
                    page=spine_idx, page_label=current_page_label,
                    confidence=Confidence.EXCELLENT,
                ))
                # Suppress descendants — Footnote text already absorbs the children.
                for d in elem.iter():
                    if d is not elem:
                        consumed_subtree.add(id(d))
        elif tag == f"{{{_XHTML_NS}}}figcaption":
            text = _text_of(elem)
            if text:
                blocks.append(FigureCaption(
                    text=text, page=spine_idx, page_label=current_page_label,
                    confidence=Confidence.EXCELLENT,
                ))

    return blocks
