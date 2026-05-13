"""EPUB metadata extractor — stdlib zipfile + xml.etree.

Implements `MetadataExtractor` for EPUBs. Reads `META-INF/container.xml`
to locate the OPF, then parses Dublin Core metadata. No external XML
library (no lxml).

See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §6.
"""
from __future__ import annotations

import logging
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

                # Subsequent tasks parse the OPF.
                return BookMetadata()
        except zipfile.BadZipFile as exc:
            logger.warning("EPUB %s zip read failed: %s", path, exc)
            return BookMetadata(
                error=ErrorCode.MALFORMED_EPUB,
                warnings=[MetadataWarning(
                    code=WarningCode.INCOMPLETE_EXTRACTION, detail=str(exc),
                )],
            )
