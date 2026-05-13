"""EPUB metadata extractor — stdlib zipfile + xml.etree.

Implements `MetadataExtractor` for EPUBs. Reads `META-INF/container.xml`
to locate the OPF, then parses Dublin Core metadata. No external XML
library (no lxml).

See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §6.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from book_ingestion.metadata import (
    BookMetadata,
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

                return BookMetadata(
                    title=title,
                    full_title=title,
                    publisher=publisher,
                    language=language,
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
