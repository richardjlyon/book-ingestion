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


def _write_zip(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be uncompressed and first per the EPUB spec
        if "mimetype" in files:
            zf.writestr(zipfile.ZipInfo("mimetype"), files["mimetype"], compress_type=zipfile.ZIP_STORED)
        for name, content in files.items():
            if name == "mimetype":
                continue
            zf.writestr(name, content)
