"""Chapter reconciliation for EPUBs: nav → spine → headings.

See `docs/superpowers/specs/2026-05-14-m2.1-epub-ir-design.md` §5.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

from book_ingestion.ir import (
    Chapter,
    Confidence,
    MapInfo,
    Provenance,
    SpineRange,
)

_OPF_NS = "http://www.idpf.org/2007/opf"
_XHTML_NS = "http://www.w3.org/1999/xhtml"

_CONTENT_MEDIA_TYPES = frozenset({"application/xhtml+xml", "text/html"})
_FILENAME_HUMANISE_RE = re.compile(r"^\d+[_\-\s]*|\.[^.]+$")


@dataclass(frozen=True)
class SpineItem:
    """A single OPF <spine> entry resolved against the manifest."""
    idx: int                  # 1-based after content-XHTML filter
    href: str                 # full zip-internal path (e.g. "OEBPS/ch1.xhtml")
    media_type: str
    raw_idref: str            # the OPF idref attribute (debug aid)


@dataclass(frozen=True)
class NavEntry:
    """A top-level nav.xhtml or NCX entry."""
    title: str
    target_href: str          # the href as it appears in nav (relative to nav file)
    target_frag: str | None   # fragment after '#', or None


def extract_spine(opf_root: ET.Element, *, opf_dir: str) -> list[SpineItem]:
    """Walk OPF <spine> + <manifest>, returning content-XHTML items in order, 1-based."""
    # Manifest: idref -> (href, media-type)
    manifest: dict[str, tuple[str, str]] = {}
    for item in opf_root.iter(f"{{{_OPF_NS}}}item"):
        item_id = item.get("id") or ""
        href = item.get("href") or ""
        media = item.get("media-type") or ""
        if item_id and href:
            manifest[item_id] = (href, media)

    items: list[SpineItem] = []
    for itemref in opf_root.iter(f"{{{_OPF_NS}}}itemref"):
        idref = itemref.get("idref") or ""
        if idref not in manifest:
            continue
        href, media = manifest[idref]
        if media not in _CONTENT_MEDIA_TYPES:
            continue
        full_path = f"{opf_dir}/{href}" if opf_dir and not href.startswith(opf_dir + "/") else href
        items.append(SpineItem(
            idx=len(items) + 1, href=full_path, media_type=media, raw_idref=idref,
        ))
    return items


def _humanise_filename(path: str) -> str:
    """`'OEBPS/03_chapter_one.xhtml'` → `'Chapter One'`."""
    base = path.rsplit("/", 1)[-1]
    stem = _FILENAME_HUMANISE_RE.sub("", base)
    return stem.replace("_", " ").replace("-", " ").strip().title() or base


def _first_heading_in_xhtml(zf: zipfile.ZipFile, href: str) -> str | None:
    """Return the text of the first `<h1>` or `<h2>` found in `href`, or None."""
    try:
        content = zf.read(href)
    except KeyError:
        return None
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    for tag in (f"{{{_XHTML_NS}}}h1", f"{{{_XHTML_NS}}}h2"):
        for h in root.iter(tag):
            text = "".join(h.itertext()).strip()
            if text:
                return text
    return None


def _spine_only_assembly(
    spine: list[SpineItem],
    zf: zipfile.ZipFile,
) -> tuple[list[Chapter], MapInfo, set[str]]:
    """Step 4 — one chapter per filtered-spine item."""
    chapters: list[Chapter] = []
    for item in spine:
        title = _first_heading_in_xhtml(zf, item.href) or _humanise_filename(item.href)
        chapters.append(Chapter(
            index=item.idx - 1,
            title=title,
            locator=SpineRange(start_spine=item.idx, end_spine=item.idx),
            provenance=Provenance.INFERRED,
            confidence=Confidence.FAIR,
        ))
    map_info = MapInfo(
        provenance=Provenance.INFERRED,
        confidence=Confidence.FAIR,
        method="epub_spine",
    )
    return chapters, map_info, {"spine_only"}


def build_chapter_map_epub(
    *,
    spine: list[SpineItem],
    nav: list[NavEntry] | None,
    zf: zipfile.ZipFile,
    opf_dir: str,
) -> tuple[list[Chapter], MapInfo, set[str]]:
    """Top-level entry — chooses the path per spec §5 Step 2.

    Returns (chapters, map_info, flag_set). The flag_set is the additional
    flags the recipe contributes; the backend assembles the final flag list.
    """
    if not spine:
        return [], MapInfo(provenance=Provenance.NONE, confidence=Confidence.POOR, method="none"), {"toc_unresolved"}

    if nav is None or len([e for e in nav if e.target_href]) < 2:
        return _spine_only_assembly(spine, zf)

    # Nav-driven path lands in Task 6
    raise NotImplementedError("nav-driven path lands in Task 6")
