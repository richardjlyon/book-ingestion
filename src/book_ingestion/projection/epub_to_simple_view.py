"""Project XHTML element trees into simple_view blocks.

See `docs/superpowers/specs/2026-05-14-m2.1-epub-ir-design.md` §6.

Stateful document-order walker:
- page anchors (<a class="page">, <span epub:type="pagebreak">) consume into
  current_page_label and are NOT emitted as blocks
- nav, cover, titlepage, toc, page-list elements are skipped entirely
- start_frag / end_frag bound emission for fragment-bounded chapter slices
- xhtml parse failure emits a single failed_region with raw-text salvage

Known deferrals (future):
- <pre> blocks are not yet handled — spec §3.3 calls for them to become
  Paragraphs with verbatim content, but _text_of currently collapses
  whitespace. Trade non-fiction (the M2.1 acceptance fixture genre)
  effectively never carries code blocks.
- Inline page anchors inside leaf-emitting elements (e.g. `<p>Text <a class="page"
  id="page-7"/> more.</p>`) are NOT consumed: the walker emits the Paragraph
  and does not recurse into its children, so the page anchor is missed.
  Fixing this requires walking into leaf elements just to find page anchors,
  which conflicts with the leaf-emit-and-don't-recurse pattern. Acceptable for
  M2.1 because Pappé and Shlaim place page anchors at block level (between
  paragraphs), not inline within paragraphs. Real-world fixtures with inline
  anchors should drive the next iteration.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import TypedDict

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

_BOILERPLATE_EPUB_TYPES = frozenset({"cover", "titlepage", "toc", "nav", "page-list", "landmarks"})
_BOILERPLATE_TAGS = frozenset({f"{{{_XHTML_NS}}}nav"})


class _WalkerState(TypedDict):
    current_page_label: str | None
    in_range: bool
    start_frag: str | None
    end_frag: str | None
    blocks: list[Block]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _text_of(elem: ET.Element) -> str:
    parts = list(elem.itertext())
    joined = "".join(parts)
    return re.sub(r"\s+", " ", joined).strip()


def _table_rows(elem: ET.Element) -> list[list[str]]:
    rows: list[list[str]] = []

    def _collect_rows_from(container: ET.Element) -> None:
        for child in container:
            if _local(child.tag) == "tr":
                cells: list[str] = []
                for c in child:
                    if _local(c.tag) in ("td", "th"):
                        cells.append(_text_of(c))
                if cells:
                    rows.append(cells)

    _collect_rows_from(elem)
    for section in elem:
        if _local(section.tag) in ("thead", "tbody", "tfoot"):
            _collect_rows_from(section)
    return rows


def _is_boilerplate(elem: ET.Element) -> bool:
    if elem.tag in _BOILERPLATE_TAGS:
        return True
    epub_type = (elem.get(f"{{{_EPUB_NS}}}type") or "").strip()
    return epub_type in _BOILERPLATE_EPUB_TYPES


def _read_page_label(elem: ET.Element, page_label_map: dict[str, str]) -> str | None:
    """If `elem` is a page anchor, return its printed-page label; else None.

    Recognised patterns:
    - <a class="page" id="page-N"/>
    - <a id="page-N"/> (with or without class)
    - <span epub:type="pagebreak" id="..." title="N"/>
    The page_label_map (from read_pageList_anchors) is consulted first; falls
    back to id-stripping or the title/aria-label attribute.
    """
    tag_local = _local(elem.tag)
    elem_id = elem.get("id") or ""
    epub_type = (elem.get(f"{{{_EPUB_NS}}}type") or "").strip()

    if tag_local == "a" and elem_id.startswith("page-"):
        if elem_id in page_label_map:
            return page_label_map[elem_id]
        return elem_id[len("page-"):]
    if epub_type == "pagebreak":
        if elem_id and elem_id in page_label_map:
            return page_label_map[elem_id]
        return (
            elem.get("title")
            or elem.get("aria-label")
            or (elem_id[len("page-"):] if elem_id.startswith("page-") else None)
        )
    return None


def _emit_for_element(
    elem: ET.Element,
    *,
    spine_idx: int,
    current_page_label: str | None,
    block_count: int,
) -> list[Block] | None:
    """Return Block(s) for a leaf-emitting element, OR None to signal "recurse".

    Returns:
      - [Block, ...] (possibly empty) when this element type is leaf-emitting.
      - None when the element is a generic container — the walker should recurse.
    """
    tag = elem.tag
    if tag in _HEADING_TAGS:
        text = _text_of(elem)
        return [Heading(
            text=text, level=_HEADING_TAGS[tag],
            page=spine_idx, page_label=current_page_label,
            confidence=Confidence.EXCELLENT,
        )] if text else []
    if tag == f"{{{_XHTML_NS}}}p":
        text = _text_of(elem)
        return [Paragraph(
            text=text, page=spine_idx, page_label=current_page_label,
            confidence=Confidence.EXCELLENT,
        )] if text else []
    if tag == f"{{{_XHTML_NS}}}blockquote":
        # If <p>s are nested, recurse so each <p> emits its own block.
        if list(elem.iter(f"{{{_XHTML_NS}}}p")):
            return None
        text = _text_of(elem)
        return [Paragraph(
            text=text, page=spine_idx, page_label=current_page_label,
            confidence=Confidence.EXCELLENT,
        )] if text else []
    if tag == f"{{{_XHTML_NS}}}table":
        rows = _table_rows(elem)
        raw_text = "\n".join(" | ".join(r) for r in rows)
        return [Table(
            page=spine_idx, page_label=current_page_label,
            confidence=Confidence.EXCELLENT,
            rows=rows or None, raw_text=raw_text,
        )]
    if tag == f"{{{_XHTML_NS}}}aside":
        if (elem.get(f"{{{_EPUB_NS}}}type") or "").strip() == "footnote":
            return [Footnote(
                id=elem.get("id") or f"fn-{block_count}",
                text=_text_of(elem),
                page=spine_idx, page_label=current_page_label,
                confidence=Confidence.EXCELLENT,
            )]
        return []  # non-footnote aside: skip (don't recurse — could be sidebar boilerplate)
    if tag == f"{{{_XHTML_NS}}}figcaption":
        text = _text_of(elem)
        return [FigureCaption(
            text=text, page=spine_idx, page_label=current_page_label,
            confidence=Confidence.EXCELLENT,
        )] if text else []
    return None  # signal "recurse"


def _walk_block_level(
    parent: ET.Element,
    *,
    spine_idx: int,
    page_label_map: dict[str, str],
    state: _WalkerState,
) -> None:
    """Document-order recursive walk emitting block-level entries.

    state = {
        "current_page_label": str | None,
        "in_range": bool,             # True when between start_frag and end_frag
        "start_frag": str | None,     # None means "from top"
        "end_frag": str | None,       # None means "to bottom"
        "blocks": list[Block],
    }
    """
    for elem in list(parent):
        elem_id = elem.get("id") or ""

        # End-frag check: stop emission when we hit the end fragment marker.
        if state["end_frag"] is not None and elem_id == state["end_frag"]:
            state["in_range"] = False

        # Start-frag check: begin emission when we hit the start fragment marker.
        if not state["in_range"] and state["start_frag"] is not None and elem_id == state["start_frag"]:
            state["in_range"] = True

        # If start_frag is set and we haven't found it yet, recurse to look deeper.
        if not state["in_range"] and state["start_frag"] is not None:
            _walk_block_level(elem, spine_idx=spine_idx, page_label_map=page_label_map, state=state)
            continue

        if not state["in_range"]:
            continue

        # Page anchor consumption (does not emit a block, does not recurse)
        page_lbl = _read_page_label(elem, page_label_map)
        if page_lbl is not None:
            state["current_page_label"] = page_lbl
            continue

        # Boilerplate skip — entire subtree dropped
        if _is_boilerplate(elem):
            continue

        # Element emission decision
        emitted = _emit_for_element(
            elem, spine_idx=spine_idx,
            current_page_label=state["current_page_label"],
            block_count=len(state["blocks"]),
        )
        if emitted is None:
            # Generic container — recurse into children
            _walk_block_level(elem, spine_idx=spine_idx, page_label_map=page_label_map, state=state)
        else:
            state["blocks"].extend(emitted)
            # Leaf-emitting element: do NOT recurse into children


def project_xhtml_to_blocks(
    *,
    xhtml_bytes: bytes,
    spine_idx: int,
    page_label_map: dict[str, str],
    start_frag: str | None = None,
    end_frag: str | None = None,
) -> list[Block]:
    """Walk an XHTML document and emit a list of simple_view blocks."""
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

    body_elem = root.find(f"{{{_XHTML_NS}}}body")
    body = body_elem if body_elem is not None else root
    blocks: list[Block] = []
    state: _WalkerState = {
        "current_page_label": None,
        "in_range": start_frag is None,  # start emitting immediately when no start_frag
        "start_frag": start_frag,
        "end_frag": end_frag,
        "blocks": blocks,
    }
    _walk_block_level(body, spine_idx=spine_idx, page_label_map=page_label_map, state=state)
    return blocks
