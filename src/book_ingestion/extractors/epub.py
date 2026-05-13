"""EPUB metadata extractor — stdlib zipfile + xml.etree.

Implements `MetadataExtractor` for EPUBs. Reads `META-INF/container.xml`
to locate the OPF, then parses Dublin Core metadata. No external XML
library (no lxml).

See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §6.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from book_ingestion.metadata import (
    BookMetadata,
    Creator,
    CreatorRole,
    ErrorCode,
    MetadataWarning,
    WarningCode,
)

logger = logging.getLogger(__name__)

_ADOBE_DRM_NS = "http://ns.adobe.com/adept"
_APPLE_DRM_NS = "com.apple.iBooks"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_OPF_NS = "http://www.idpf.org/2007/opf"
_CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"

_OPF_ROLE_MAP: dict[str, CreatorRole] = {
    "aut": CreatorRole.AUTHOR,
    "edt": CreatorRole.EDITOR,
    "trl": CreatorRole.TRANSLATOR,
    "ill": CreatorRole.ILLUSTRATOR,
}


def _strip_creator_punct(raw: str) -> tuple[str, bool]:
    """Strip trailing whitespace + ; , and . from a creator string.

    Returns (stripped, flag_warning) — flag is True only when `;` or `,` was stripped.
    """
    s = raw
    flag = False
    # First trim trailing whitespace and periods silently
    while s and s[-1] in (" ", "\t", "."):
        s = s[:-1]
    # Then strip ; and , and flag
    while s and s[-1] in (";", ","):
        flag = True
        s = s[:-1]
    # Strip remaining trailing whitespace again
    s = s.rstrip()
    return s, flag


def _parse_one_creator_string(raw: str, role: CreatorRole) -> Creator:
    """Parse 'Last, First' or 'First Last' into a Creator. raw is preserved."""
    stripped, _ = _strip_creator_punct(raw)
    if "," in stripped:
        last, _, first = stripped.partition(",")
        last_name = last.strip() or None
        first_name = first.strip().rstrip(".") or None
    else:
        parts = stripped.rsplit(None, 1)
        if len(parts) == 2:
            first_name = parts[0].strip() or None
            last_name = parts[1].strip() or None
        else:
            first_name, last_name = None, stripped or None
    return Creator(role=role, first_name=first_name, last_name=last_name, raw=raw)


def _split_multi_creator(s: str) -> list[str]:
    """Split 'Smith, J. and Jones, K.' into ['Smith, J.', 'Jones, K.']."""
    return [p.strip() for p in re.split(r"\s+and\s+", s) if p.strip()]


def _extract_creators_from_opf(
    meta_elem: ET.Element,
    warnings: list[MetadataWarning],
) -> list[Creator]:
    """Walk dc:creator elements in document order; resolve role; split multi-creator strings."""
    creators: list[Creator] = []
    # Build EPUB3 refines map: id -> role (for <meta refines="#id" property="role">aut</meta>)
    refines_role: dict[str, str] = {}
    for meta in meta_elem.findall(f"{{{_OPF_NS}}}meta"):
        refines = meta.get("refines", "")
        if meta.get("property") == "role" and refines.startswith("#"):
            text = (meta.text or "").strip()
            if text:
                refines_role[refines[1:]] = text

    for elem in meta_elem.findall(f"{{{_DC_NS}}}creator"):
        text = elem.text or ""
        if not text.strip():
            continue
        # Resolve role
        role_str = elem.get(f"{{{_OPF_NS}}}role") or refines_role.get(elem.get("id", ""), "aut")
        role = _OPF_ROLE_MAP.get(role_str, CreatorRole.AUTHOR)

        # Prefer opf:file-as if present
        file_as = elem.get(f"{{{_OPF_NS}}}file-as")
        base_text = file_as if file_as else text

        # Punctuation flag
        _stripped, flag = _strip_creator_punct(base_text)
        if flag and not any(w.code == WarningCode.DC_CREATOR_TRAILING_PUNCTUATION for w in warnings):
            warnings.append(MetadataWarning(
                code=WarningCode.DC_CREATOR_TRAILING_PUNCTUATION,
                detail=f"creator '{text.strip()}' had trailing ; or ,",
            ))

        # Split multi-creator strings. For name *parsing* we prefer the
        # sort-form in opf:file-as when present (it's easier to split into
        # last/first). For the `raw` field per spec §6.3, we always preserve
        # the original element text (single-creator case) or the original
        # split part (multi-creator case) — never the file-as derivation.
        parsing_source = base_text
        raw_source_full = text  # always the element text — never file_as
        parts_for_parsing = _split_multi_creator(parsing_source)
        parts_for_raw = _split_multi_creator(raw_source_full) if len(parts_for_parsing) > 1 else [raw_source_full]
        for i, parse_part in enumerate(parts_for_parsing):
            raw_part = parts_for_raw[i] if i < len(parts_for_raw) else parse_part
            # _parse_one_creator_string parses names from `raw_part`; we then
            # set `raw` explicitly so it preserves the element-text form.
            c = _parse_one_creator_string(parse_part, role)
            creators.append(c.model_copy(update={"raw": raw_part}))

    return creators


def _find_opf_path(container_xml: bytes) -> str | None:
    """Parse container.xml to find the OPF path from rootfile/@full-path."""
    try:
        root = ET.fromstring(container_xml)
    except ET.ParseError:
        return None
    rootfile = root.find(f".//{{{_CONTAINER_NS}}}rootfile")
    if rootfile is None:
        return None
    return rootfile.get("full-path")


def _normalise_language(raw: str) -> tuple[str, bool]:
    """Normalise a BCP-47 tag to its primary subtag. Returns (out, changed)."""
    primary = raw.split("-", 1)[0].lower()
    return primary, primary != raw


class EpubMetadataExtractor:
    """EPUB metadata extractor.

    `extract_metadata` always returns a BookMetadata; it does not raise on
    file-shape failures. See spec §7.
    """

    name = "epub_stdlib"

    def extract_metadata(self, path: Path, *, pages: int = 6) -> BookMetadata:
        # `pages` is ignored for EPUB (no concept of leading pages).
        del pages
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as exc:
            logger.warning("EPUB %s is not a valid zip: %s", path, exc)
            return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

        try:
            with zf:
                names = set(zf.namelist())

                # DRM detection
                if "META-INF/encryption.xml" in names:
                    try:
                        enc_bytes = zf.read("META-INF/encryption.xml")
                        if _ADOBE_DRM_NS.encode() in enc_bytes or _APPLE_DRM_NS.encode() in enc_bytes:
                            return BookMetadata(error=ErrorCode.DRM_PROTECTED)
                    except KeyError:
                        pass

                # Missing container.xml is malformed
                if "META-INF/container.xml" not in names:
                    return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

                # Parse container.xml to find OPF path
                container_xml = zf.read("META-INF/container.xml")
                opf_path = _find_opf_path(container_xml)
                if opf_path is None or opf_path not in names:
                    return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

                # Parse OPF
                try:
                    opf_root = ET.fromstring(zf.read(opf_path))
                except ET.ParseError as exc:
                    logger.warning("EPUB OPF parse failed for %s: %s", path, exc)
                    return BookMetadata(
                        error=ErrorCode.MALFORMED_EPUB,
                        warnings=[MetadataWarning(
                            code=WarningCode.INCOMPLETE_EXTRACTION, detail=str(exc),
                        )],
                    )

                # Find metadata element
                meta_elem = opf_root.find(f".//{{{_OPF_NS}}}metadata")
                if meta_elem is None:
                    return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

                warnings: list[MetadataWarning] = []

                # Extract title
                dc_title = meta_elem.findtext(f"{{{_DC_NS}}}title")
                title = dc_title.strip() if dc_title else None

                # Extract publisher
                dc_publisher = meta_elem.findtext(f"{{{_DC_NS}}}publisher")
                publisher = dc_publisher.strip() if dc_publisher else None

                # Extract and normalise language
                dc_language = meta_elem.findtext(f"{{{_DC_NS}}}language")
                if dc_language:
                    norm, changed = _normalise_language(dc_language.strip())
                    language = norm
                    if changed:
                        warnings.append(MetadataWarning(
                            code=WarningCode.LANGUAGE_NORMALISED,
                            detail=f"{dc_language.strip()} -> {norm}",
                        ))
                else:
                    language = None

                # Extract creators
                creators = _extract_creators_from_opf(meta_elem, warnings)

                return BookMetadata(
                    title=title,
                    full_title=title,
                    publisher=publisher,
                    language=language,
                    creators=creators,
                    warnings=warnings,
                )
        except zipfile.BadZipFile as exc:
            logger.warning("EPUB %s zip read failed: %s", path, exc)
            return BookMetadata(
                error=ErrorCode.MALFORMED_EPUB,
                warnings=[MetadataWarning(
                    code=WarningCode.INCOMPLETE_EXTRACTION, detail=str(exc),
                )],
            )
