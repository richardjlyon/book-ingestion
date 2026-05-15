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


def parse_nav_or_ncx(zf: zipfile.ZipFile, *, opf_dir: str) -> list[NavEntry] | None:
    """Find nav.xhtml or toc.ncx in the zip and return its top-level entries.

    Returns None when neither is present or both fail to parse.
    """
    names = set(zf.namelist())

    # Prefer nav.xhtml (EPUB 3) — search by name suffix.
    for candidate in sorted(n for n in names if n.endswith("nav.xhtml")):
        try:
            content = zf.read(candidate)
        except KeyError:
            continue
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            continue
        for nav in root.iter(f"{{{_XHTML_NS}}}nav"):
            epub_type = (nav.get("{http://www.idpf.org/2007/ops}type") or "").strip()
            if epub_type and epub_type != "toc":
                continue
            entries: list[NavEntry] = []
            # Top-level <ol><li><a>; deeper nesting ignored
            for ol in nav.iter(f"{{{_XHTML_NS}}}ol"):
                for li in ol.findall(f"{{{_XHTML_NS}}}li"):
                    a = li.find(f"{{{_XHTML_NS}}}a")
                    if a is None:
                        continue
                    target = a.get("href") or ""
                    title = "".join(a.itertext()).strip()
                    if not target or not title:
                        continue
                    href, _, frag = target.partition("#")
                    entries.append(NavEntry(
                        title=title, target_href=href, target_frag=frag or None,
                    ))
                break  # first <ol> only — top-level
            if entries:
                return entries

    # Fall back to toc.ncx (EPUB 2)
    for candidate in sorted(n for n in names if n.endswith(".ncx")):
        try:
            content = zf.read(candidate)
        except KeyError:
            continue
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            continue
        ncx_ns = "http://www.daisy.org/z3986/2005/ncx/"
        navmap = root.find(f"{{{ncx_ns}}}navMap")
        if navmap is None:
            continue
        ncx_entries: list[NavEntry] = []
        for navpoint in navmap.findall(f"{{{ncx_ns}}}navPoint"):
            label_elem = navpoint.find(f"{{{ncx_ns}}}navLabel/{{{ncx_ns}}}text")
            content_elem = navpoint.find(f"{{{ncx_ns}}}content")
            if label_elem is None or content_elem is None:
                continue
            title = (label_elem.text or "").strip()
            target = content_elem.get("src") or ""
            if not title or not target:
                continue
            href, _, frag = target.partition("#")
            ncx_entries.append(NavEntry(
                title=title, target_href=href, target_frag=frag or None,
            ))
        if ncx_entries:
            return ncx_entries

    return None


def _resolve_nav_target_to_spine(
    nav_target_href: str,
    spine: list[SpineItem],
    opf_dir: str,
) -> int | None:
    """Map a nav entry's href to its 1-based spine index, or None if unresolved."""
    full = (
        f"{opf_dir}/{nav_target_href}"
        if opf_dir and not nav_target_href.startswith(opf_dir + "/")
        else nav_target_href
    )
    for s in spine:
        if s.href == full:
            return s.idx
    return None


def _nav_driven_assembly(
    spine: list[SpineItem],
    nav: list[NavEntry],
    opf_dir: str,
) -> tuple[list[Chapter], MapInfo, set[str]]:
    """Step 3 — nav-driven chapter assembly."""
    flags: set[str] = {"nav_used"}
    chapters: list[Chapter] = []

    # Pre-resolve every nav entry's target spine index (drop unresolvable).
    resolved: list[tuple[NavEntry, int]] = []
    for e in nav:
        idx = _resolve_nav_target_to_spine(e.target_href, spine, opf_dir)
        if idx is not None:
            resolved.append((e, idx))

    if len(resolved) < 2:
        # Defensive fallback — dispatcher should have caught this.
        return [], MapInfo(provenance=Provenance.NONE, confidence=Confidence.POOR, method="none"), {"spine_only"}

    last_spine_idx = spine[-1].idx

    for i, (entry, this_idx) in enumerate(resolved):
        # Determine the spine extent of this chapter
        if i + 1 < len(resolved):
            next_entry: NavEntry | None
            next_entry, next_idx = resolved[i + 1]
        else:
            next_entry, next_idx = None, last_spine_idx + 1

        if entry.target_frag is None:
            # Whole-file chapter: spans up to (next_idx - 1)
            end_spine = max(this_idx, next_idx - 1)
            if end_spine > this_idx:
                flags.add("chapter_spans_multiple_files")
            locator = SpineRange(
                start_spine=this_idx, end_spine=end_spine,
                start_frag=None, end_frag=None,
            )
        else:
            # Chapter starts mid-file via fragment
            flags.add("headings_split_used")
            if next_entry is not None and next_entry.target_frag is not None and next_idx == this_idx:
                # Sibling chapter inside the same file
                end_spine = this_idx
                end_frag: str | None = next_entry.target_frag
            else:
                # Sibling is in a later file (or no sibling) — chapter consumes from frag to end
                end_spine = max(this_idx, next_idx - 1)
                end_frag = None
                if end_spine > this_idx:
                    flags.add("chapter_spans_multiple_files")
            locator = SpineRange(
                start_spine=this_idx, end_spine=end_spine,
                start_frag=entry.target_frag, end_frag=end_frag,
            )

        chapters.append(Chapter(
            index=i,
            title=entry.title,
            locator=locator,
            provenance=Provenance.EMBEDDED,
            confidence=Confidence.EXCELLENT,
        ))

    map_info = MapInfo(
        provenance=Provenance.EMBEDDED,
        confidence=Confidence.GOOD,
        method="epub_nav",
    )
    return chapters, map_info, flags


def _headings_only_assembly(
    opf_root: ET.Element,
    zf: zipfile.ZipFile,
    opf_dir: str,
) -> tuple[list[Chapter], MapInfo, set[str]]:
    """Step 5 — last-resort. Walk all manifest XHTML files in order,
    treating each <h1> as a chapter boundary."""
    chapters: list[Chapter] = []
    synth_idx = 0  # synthetic 1-based spine index for SpineRange

    manifest_files: list[str] = []
    for item in opf_root.iter(f"{{{_OPF_NS}}}item"):
        href = item.get("href") or ""
        media = item.get("media-type") or ""
        if media not in _CONTENT_MEDIA_TYPES or not href:
            continue
        full = f"{opf_dir}/{href}" if opf_dir and not href.startswith(opf_dir + "/") else href
        manifest_files.append(full)

    for f in manifest_files:
        try:
            content = zf.read(f)
        except KeyError:
            continue
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            continue
        synth_idx += 1
        for h in root.iter(f"{{{_XHTML_NS}}}h1"):
            text = "".join(h.itertext()).strip()
            if not text:
                continue
            chapters.append(Chapter(
                index=len(chapters),
                title=text,
                locator=SpineRange(start_spine=synth_idx, end_spine=synth_idx),
                provenance=Provenance.INFERRED,
                confidence=Confidence.FAIR,
            ))

    if not chapters:
        return [], MapInfo(provenance=Provenance.NONE, confidence=Confidence.POOR, method="none"), {"toc_unresolved"}

    map_info = MapInfo(
        provenance=Provenance.INFERRED,
        confidence=Confidence.FAIR,
        method="epub_headings",
    )
    return chapters, map_info, {"toc_unresolved"}


def build_chapter_map_epub(
    *,
    spine: list[SpineItem],
    nav: list[NavEntry] | None,
    zf: zipfile.ZipFile,
    opf_dir: str,
    opf_root: ET.Element | None = None,
) -> tuple[list[Chapter], MapInfo, set[str]]:
    """Top-level entry — chooses the path per spec §5 Step 2."""
    if not spine:
        if opf_root is not None:
            return _headings_only_assembly(opf_root, zf, opf_dir)
        return [], MapInfo(provenance=Provenance.NONE, confidence=Confidence.POOR, method="none"), {"toc_unresolved"}

    resolved_count = 0
    if nav is not None:
        for e in nav:
            if _resolve_nav_target_to_spine(e.target_href, spine, opf_dir) is not None:
                resolved_count += 1

    if nav is None or resolved_count < 2:
        return _spine_only_assembly(spine, zf)

    return _nav_driven_assembly(spine, nav, opf_dir)
