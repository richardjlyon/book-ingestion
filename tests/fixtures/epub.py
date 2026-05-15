"""Synthetic EPUB builders for tests. stdlib only (zipfile + xml strings).

Each builder produces a minimal-but-valid EPUB exercising a specific path:
- build_epub: well-formed EPUB2 with given metadata.
- build_epub_with_truncated_title: dc:title is bare; full title on title-page xhtml.
- build_epub_with_drm: META-INF/encryption.xml present with Adobe DRM namespace.
- build_malformed_epub: missing OPF (no container.xml entry).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

_CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="{opf_path}" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_OPF_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    {metadata_inner}
  </metadata>
  <manifest>
    {manifest_inner}
  </manifest>
  <spine toc="ncx">
    {spine_inner}
  </spine>
  {guide_block}
</package>
"""

_TITLE_PAGE_XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>{title}</title></head>
  <body><h1>{title}</h1></body>
</html>
"""

_DRM_ENCRYPTION_XML = """<?xml version="1.0"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <EncryptedData xmlns="http://www.w3.org/2001/04/xmlenc#"
                 xmlns:adept="http://ns.adobe.com/adept">
    <EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>
  </EncryptedData>
</encryption>
"""


def build_epub(
    path: Path,
    *,
    dc_title: str,
    creators: list[tuple[str, str]],   # (text, opf:role)
    isbn: str | None,
    publisher: str | None,
    language: str,
    eisbn: str | None = None,
    date: str | None = None,
) -> Path:
    """Build a minimal EPUB2 with the supplied metadata."""
    metadata_lines: list[str] = [f'<dc:title>{dc_title}</dc:title>']
    for text, role in creators:
        metadata_lines.append(f'<dc:creator opf:role="{role}">{text}</dc:creator>')
    if publisher:
        metadata_lines.append(f'<dc:publisher>{publisher}</dc:publisher>')
    metadata_lines.append(f'<dc:language>{language}</dc:language>')
    if isbn:
        metadata_lines.append(f'<dc:identifier id="bookid" opf:scheme="ISBN">{isbn}</dc:identifier>')
        metadata_lines.append(f'<meta name="isbn" content="{isbn}"/>')
    if eisbn:
        metadata_lines.append(f'<meta name="eisbn" content="{eisbn}"/>')
    if date:
        metadata_lines.append(f'<dc:date opf:event="publication">{date}</dc:date>')

    opf = _OPF_TEMPLATE.format(
        metadata_inner="\n    ".join(metadata_lines),
        manifest_inner='<item id="t" href="title.xhtml" media-type="application/xhtml+xml"/>',
        spine_inner='<itemref idref="t"/>',
        guide_block="",
    )
    title_page = _TITLE_PAGE_XHTML.format(title=dc_title)

    _write_zip(
        path,
        {
            "mimetype": "application/epub+zip",
            "META-INF/container.xml": _CONTAINER_XML.format(opf_path="OEBPS/content.opf"),
            "OEBPS/content.opf": opf,
            "OEBPS/title.xhtml": title_page,
        },
    )
    return path


def build_epub_with_truncated_title(
    path: Path,
    *,
    dc_title: str,
    full_title_in_xhtml: str,
) -> Path:
    """Build an EPUB whose <dc:title> is bare; the title page xhtml has the full title."""
    metadata_lines = [
        f'<dc:title>{dc_title}</dc:title>',
        '<dc:language>en</dc:language>',
    ]
    opf = _OPF_TEMPLATE.format(
        metadata_inner="\n    ".join(metadata_lines),
        manifest_inner='<item id="t" href="title.xhtml" media-type="application/xhtml+xml"/>',
        spine_inner='<itemref idref="t"/>',
        guide_block='<guide><reference type="title-page" href="title.xhtml" title="Title"/></guide>',
    )
    title_page = _TITLE_PAGE_XHTML.format(title=full_title_in_xhtml)
    _write_zip(
        path,
        {
            "mimetype": "application/epub+zip",
            "META-INF/container.xml": _CONTAINER_XML.format(opf_path="OEBPS/content.opf"),
            "OEBPS/content.opf": opf,
            "OEBPS/title.xhtml": title_page,
        },
    )
    return path


def build_epub_with_split_title_page(
    path: Path,
    *,
    dc_title: str,
    h1_text: str,
    h2_text: str,
) -> Path:
    """Build an EPUB whose title-page xhtml has separate h1 (title) and h2 (subtitle).

    dc:title is bare (no subtitle); the full title is synthesised from h1+h2 by
    _parse_title_page_text when the h1 matches dc:title.
    """
    metadata_lines = [
        f'<dc:title>{dc_title}</dc:title>',
        '<dc:language>en</dc:language>',
    ]
    opf = _OPF_TEMPLATE.format(
        metadata_inner="\n    ".join(metadata_lines),
        manifest_inner='<item id="t" href="title.xhtml" media-type="application/xhtml+xml"/>',
        spine_inner='<itemref idref="t"/>',
        guide_block='<guide><reference type="title-page" href="title.xhtml" title="Title"/></guide>',
    )
    title_page = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        f'<head><title>{dc_title}</title></head>'
        f'<body><h1>{h1_text}</h1><h2>{h2_text}</h2></body>'
        '</html>'
    )
    _write_zip(
        path,
        {
            "mimetype": "application/epub+zip",
            "META-INF/container.xml": _CONTAINER_XML.format(opf_path="OEBPS/content.opf"),
            "OEBPS/content.opf": opf,
            "OEBPS/title.xhtml": title_page,
        },
    )
    return path


def build_epub_with_drm(path: Path) -> Path:
    """Build an EPUB with Adobe DRM markers in META-INF/encryption.xml."""
    _write_zip(
        path,
        {
            "mimetype": "application/epub+zip",
            "META-INF/container.xml": _CONTAINER_XML.format(opf_path="OEBPS/content.opf"),
            "META-INF/encryption.xml": _DRM_ENCRYPTION_XML,
            "OEBPS/content.opf": "<package/>",
        },
    )
    return path


def build_malformed_epub(path: Path) -> Path:
    """Build a ZIP that looks like an EPUB but has no container.xml."""
    _write_zip(path, {"mimetype": "application/epub+zip"})
    return path


_NAV_XHTML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>Contents</title></head>
  <body>
    <nav epub:type="toc">
      <ol>
{toc_items}
      </ol>
    </nav>
{page_list_block}
  </body>
</html>
"""

_NAV_PAGE_LIST_TEMPLATE = """    <nav epub:type="page-list">
      <ol>
{page_items}
      </ol>
    </nav>
"""

_NCX_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="bookid"/></head>
  <docTitle><text>{book_title}</text></docTitle>
  <navMap>
{nav_points}
  </navMap>
</ncx>
"""

_CONTENT_XHTML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>{title}</title></head>
  <body>
{body}
  </body>
</html>
"""


def build_epub_with_chapters(
    path: Path,
    *,
    dc_title: str = "Test Book",
    chapters: list[dict] | None = None,
    nav_entries: list[dict] | None = None,
    page_list: list[tuple[str, str]] | None = None,
    epub3: bool = True,
) -> Path:
    """Build a multi-spine EPUB with explicit chapters + nav.

    `chapters`: list of {id, href, title, body_xhtml} dicts — one per spine item.
    `nav_entries`: list of {title, target_href, target_frag} dicts — top-level TOC.
                   When None, derived from `chapters` (one entry per chapter).
    `page_list`: list of (printed_label, target_href_with_fragment) tuples for
                 EPUB 3 pageList nav. When None, no pageList is emitted.
    `epub3`: True → emit nav.xhtml; False → emit toc.ncx (EPUB 2 path).
    """
    chapters = chapters or [
        {"id": "c1", "href": "ch1.xhtml", "title": "Chapter 1",
         "body_xhtml": "<h1>Chapter 1</h1><p>First chapter body.</p>"},
        {"id": "c2", "href": "ch2.xhtml", "title": "Chapter 2",
         "body_xhtml": "<h1>Chapter 2</h1><p>Second chapter body.</p>"},
    ]
    nav_entries = nav_entries if nav_entries is not None else [
        {"title": c["title"], "target_href": c["href"], "target_frag": None}
        for c in chapters
    ]

    manifest_items: list[str] = []
    spine_items: list[str] = []
    files: dict[str, str] = {
        "mimetype": "application/epub+zip",
        "META-INF/container.xml": _CONTAINER_XML.format(opf_path="OEBPS/content.opf"),
    }

    for c in chapters:
        manifest_items.append(
            f'<item id="{c["id"]}" href="{c["href"]}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'<itemref idref="{c["id"]}"/>')
        files[f"OEBPS/{c['href']}"] = _CONTENT_XHTML_TEMPLATE.format(
            title=c["title"], body=c["body_xhtml"],
        )

    if epub3:
        manifest_items.append(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        )
        toc_items = "\n".join(
            f'        <li><a href="{e["target_href"]}'
            f'{("#" + e["target_frag"]) if e.get("target_frag") else ""}">{e["title"]}</a></li>'
            for e in nav_entries
        )
        if page_list:
            page_items = "\n".join(
                f'        <li><a href="{href}">{label}</a></li>'
                for label, href in page_list
            )
            page_list_block = _NAV_PAGE_LIST_TEMPLATE.format(page_items=page_items)
        else:
            page_list_block = ""
        files["OEBPS/nav.xhtml"] = _NAV_XHTML_TEMPLATE.format(
            toc_items=toc_items, page_list_block=page_list_block,
        )
    else:
        manifest_items.append(
            '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
        )
        nav_points = "\n".join(
            f'    <navPoint id="np{i}" playOrder="{i+1}">'
            f'<navLabel><text>{e["title"]}</text></navLabel>'
            f'<content src="{e["target_href"]}'
            f'{("#" + e["target_frag"]) if e.get("target_frag") else ""}"/>'
            f'</navPoint>'
            for i, e in enumerate(nav_entries)
        )
        files["OEBPS/toc.ncx"] = _NCX_TEMPLATE.format(
            book_title=dc_title, nav_points=nav_points,
        )

    metadata_inner = (
        f'<dc:title>{dc_title}</dc:title>\n    '
        '<dc:language>en</dc:language>\n    '
        '<dc:identifier id="bookid">test-book-id</dc:identifier>'
    )
    spine_attr = "" if epub3 else ' toc="ncx"'
    opf = _OPF_TEMPLATE.replace(
        '<spine toc="ncx">', f'<spine{spine_attr}>',
    ).format(
        metadata_inner=metadata_inner,
        manifest_inner="\n    ".join(manifest_items),
        spine_inner="\n    ".join(spine_items),
        guide_block="",
    )
    files["OEBPS/content.opf"] = opf

    _write_zip(path, files)
    return path


def build_epub_with_inline_page_anchors(
    path: Path,
    *,
    dc_title: str = "Anchor Book",
) -> Path:
    """Build an EPUB whose content XHTML carries in-content `<a class="page" id="page-N"/>` anchors."""
    body = (
        '<a class="page" id="page-7"/>'
        '<h1>Chapter 1</h1>'
        '<p>Para before page 8.</p>'
        '<a class="page" id="page-8"/>'
        '<p>Para on page 8.</p>'
        '<span epub:type="pagebreak" id="page-9" title="9"/>'
        '<p>Para on page 9.</p>'
    )
    return build_epub_with_chapters(
        path,
        dc_title=dc_title,
        chapters=[{"id": "c1", "href": "ch1.xhtml", "title": "Chapter 1", "body_xhtml": body}],
    )


def build_epub_with_malformed_xhtml(
    path: Path,
    *,
    dc_title: str = "Broken Book",
) -> Path:
    """Build an EPUB whose only content file fails to parse as XML."""
    files = {
        "mimetype": "application/epub+zip",
        "META-INF/container.xml": _CONTAINER_XML.format(opf_path="OEBPS/content.opf"),
        "OEBPS/content.opf": _OPF_TEMPLATE.format(
            metadata_inner=f'<dc:title>{dc_title}</dc:title><dc:language>en</dc:language>',
            manifest_inner='<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>',
            spine_inner='<itemref idref="c1"/>',
            guide_block="",
        ),
        # Deliberately malformed: unclosed tag, no XML declaration
        "OEBPS/ch1.xhtml": "<html><body><p>Unclosed paragraph<h1>broken",
    }
    _write_zip(path, files)
    return path


def build_epub_with_chapter_spanning_file(
    path: Path,
    *,
    dc_title: str = "Spanning Book",
) -> Path:
    """Build an EPUB where one spine file contains 2 chapters separated by <h1>s,
    and the nav targets fragments inside that file (`ch.xhtml#chapA`, `ch.xhtml#chapB`).
    """
    body = (
        '<h1 id="chapA">Chapter A</h1>'
        '<p>Body of chapter A.</p>'
        '<h1 id="chapB">Chapter B</h1>'
        '<p>Body of chapter B.</p>'
    )
    return build_epub_with_chapters(
        path,
        dc_title=dc_title,
        chapters=[{"id": "c", "href": "ch.xhtml", "title": "Both", "body_xhtml": body}],
        nav_entries=[
            {"title": "Chapter A", "target_href": "ch.xhtml", "target_frag": "chapA"},
            {"title": "Chapter B", "target_href": "ch.xhtml", "target_frag": "chapB"},
        ],
    )


def _write_zip(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be uncompressed and first per the EPUB spec
        if "mimetype" in files:
            zf.writestr(zipfile.ZipInfo("mimetype"), files["mimetype"], compress_type=zipfile.ZIP_STORED)
        for name, content in files.items():
            if name == "mimetype":
                continue
            zf.writestr(name, content)
