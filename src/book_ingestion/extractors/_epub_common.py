"""Shared EPUB zip/OPF/DRM/pageList helpers.

Used by both `extractors/epub.py` (M2.0 metadata extraction) and
`backends/epub_native.py` (M2.1 IR backend). Single source of truth for
opening EPUB zips and parsing the OPF.

See `docs/superpowers/specs/2026-05-14-m2.1-epub-ir-design.md` §3.7.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

_ADOBE_DRM_NS = "http://ns.adobe.com/adept"
_APPLE_DRM_NS = "com.apple.iBooks"
_CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
_OPF_NS = "http://www.idpf.org/2007/opf"
_XHTML_NS = "http://www.w3.org/1999/xhtml"
_EPUB_NS = "http://www.idpf.org/2007/ops"


def open_epub_zip(path: Path) -> zipfile.ZipFile:
    """Open an EPUB as a zip. Caller closes (or uses with-statement).

    Raises `zipfile.BadZipFile` or `OSError` on read failure — caller decides
    whether to translate to a degraded payload or propagate.
    """
    return zipfile.ZipFile(path)


def find_opf_path(zf: zipfile.ZipFile) -> str | None:
    """Parse `META-INF/container.xml` and return the OPF rootfile path, or None."""
    if "META-INF/container.xml" not in zf.namelist():
        return None
    try:
        root = ET.fromstring(zf.read("META-INF/container.xml"))
    except ET.ParseError:
        return None
    rootfile = root.find(f".//{{{_CONTAINER_NS}}}rootfile")
    if rootfile is None:
        return None
    return rootfile.get("full-path")


def parse_opf_root(zf: zipfile.ZipFile, opf_path: str) -> ET.Element | None:
    """Parse the OPF document and return its root <package> element, or None."""
    try:
        return ET.fromstring(zf.read(opf_path))
    except (ET.ParseError, KeyError):
        return None


def detect_drm(zf: zipfile.ZipFile, names: set[str] | None = None) -> bool:
    """Return True when Adobe or Apple DRM markers are detected."""
    if names is None:
        names = set(zf.namelist())
    if "META-INF/encryption.xml" not in names:
        return False
    try:
        enc_bytes = zf.read("META-INF/encryption.xml")
    except KeyError:
        return False
    return _ADOBE_DRM_NS.encode() in enc_bytes or _APPLE_DRM_NS.encode() in enc_bytes


def read_pageList_anchors(
    opf_root: ET.Element,
    zf: zipfile.ZipFile,
    names: set[str],
    *,
    opf_dir: str,
) -> dict[str, str]:
    """Return {anchor_key: printed_page_label}.

    Two sources, both surfaced:

    1. EPUB 3 `<nav epub:type="page-list">` entries inside any nav.xhtml in the
       manifest. Each `<a href="content.xhtml#frag">12</a>` contributes
       `"<href_or_frag>" -> "12"`.

    2. In-content `<a id="page-N"/>` (with or without `class="page"`) and
       `<span epub:type="pagebreak" id="..." title="N"/>` markers inside any
       content XHTML in the manifest. Each contributes `"<frag_id>" -> "N"`.

    The keys are the fragment identifiers / hrefs that block-level extraction
    will encounter while walking content XHTML.

    When both sources produce the same key (e.g. nav points to `ch1.xhtml#p12`
    and the same `id="p12"` exists in-content), the in-content marker wins
    (source-2 overwrites source-1).
    """
    anchors: dict[str, str] = {}

    # Walk manifest items
    for item in opf_root.iter(f"{{{_OPF_NS}}}item"):
        href = item.get("href") or ""
        media = item.get("media-type") or ""
        if not href:
            continue
        full_path = f"{opf_dir}/{href}" if opf_dir and not href.startswith(opf_dir + "/") else href
        if full_path not in names:
            continue
        if media not in ("application/xhtml+xml", "text/html"):
            continue
        try:
            content = zf.read(full_path)
        except KeyError:
            continue
        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            continue

        # Source 1: nav epub:type="page-list" inside this file
        for nav in root.iter(f"{{{_XHTML_NS}}}nav"):
            if (nav.get(f"{{{_EPUB_NS}}}type") or "").strip() != "page-list":
                continue
            for a in nav.iter(f"{{{_XHTML_NS}}}a"):
                target = a.get("href") or ""
                label = "".join(a.itertext()).strip()
                if not target or not label:
                    continue
                # Key by fragment when present, else by raw href
                key = target.split("#", 1)[1] if "#" in target else target
                anchors[key] = label

        # Source 2: in-content page anchors / pagebreak spans
        for elem in root.iter():
            tag = elem.tag.split("}", 1)[-1]
            elem_id = elem.get("id") or ""
            epub_type = (elem.get(f"{{{_EPUB_NS}}}type") or "").strip()

            page_label: str | None = None
            if tag == "a" and elem_id.startswith("page-"):
                page_label = elem_id[len("page-"):]
            elif epub_type == "pagebreak":
                # Prefer @title, then @aria-label, then strip 'page-' from id
                page_label = (
                    elem.get("title")
                    or elem.get("aria-label")
                    or (elem_id[len("page-"):] if elem_id.startswith("page-") else None)
                )
            if page_label and elem_id:
                anchors[elem_id] = page_label

    return anchors
