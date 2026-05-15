"""The EPUB IR backend.

Survey + extract for EPUB files using stdlib zipfile + xml.etree.ElementTree.
No third-party deps, no Docling. Schema-uniform with the PDF backend.

See `docs/superpowers/specs/2026-05-14-m2.1-epub-ir-design.md`.
"""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from book_ingestion.backends.base import Context
from book_ingestion.cache import sha256_of_file
from book_ingestion.extractors._epub_common import (
    detect_drm,
    find_opf_path,
    open_epub_zip,
    parse_opf_root,
)
from book_ingestion.ir import (
    SCHEMA_VERSION,
    BookSurvey,
    ChapterContent,
    Confidence,
    MapInfo,
    Provenance,
    Quality,
    Source,
)
from book_ingestion.quality.flags import validate_flag

logger = logging.getLogger(__name__)


class EpubNativeBackend:
    """EPUB backend. survey + extract via stdlib XML walking."""

    name = "epub_native"

    def survey(self, path: Path, *, ctx: Context) -> BookSurvey:
        if ctx.use_cache:
            cached = ctx.cache.read(path, "survey.json")
            if cached is not None:
                return BookSurvey.model_validate(cached)

        survey = self._build_survey(path)
        ctx.cache.write(path, "survey.json", survey.model_dump(mode="json"))
        return survey

    def _build_survey(self, path: Path) -> BookSurvey:
        source = self._source(path)

        try:
            zf = open_epub_zip(path)
        except (zipfile.BadZipFile, OSError) as exc:
            logger.warning("EPUB %s is not a valid zip: %s", path, exc)
            return self._degraded(source, extra_flags=set())

        try:
            with zf:
                names = set(zf.namelist())
                if detect_drm(zf, names):
                    return self._degraded(source, extra_flags={"drm_protected"})

                opf_path = find_opf_path(zf)
                if opf_path is None or opf_path not in names:
                    return self._degraded(source, extra_flags=set())

                opf_root = parse_opf_root(zf, opf_path)
                if opf_root is None:
                    return self._degraded(source, extra_flags=set())

                # Nominal path lands in Task 11.
                raise NotImplementedError("nominal survey path lands in Task 11")
        except NotImplementedError:
            raise
        except Exception as exc:  # surface as degraded rather than crash CLI
            logger.exception("EPUB %s survey failed: %s", path, exc)
            return self._degraded(source, extra_flags=set())

    @staticmethod
    def _source(path: Path) -> Source:
        return Source(
            path=str(path.resolve()),
            sha256=sha256_of_file(path),
            size_bytes=path.stat().st_size,
            format="epub",
        )

    def _degraded(self, source: Source, *, extra_flags: set[str]) -> BookSurvey:
        flags = ["unparseable", *sorted(extra_flags)]
        for f in flags:
            validate_flag(f)
        return BookSurvey(
            schema_version=SCHEMA_VERSION,
            source=source,
            metadata={},
            chapters=[],
            map=MapInfo(provenance=Provenance.NONE, confidence=Confidence.POOR, method="none"),
            quality=Quality(backend=self.name, flags=flags),
            page_labels={},
            page_label_provenance=Provenance.NONE,
        )

    def extract_chapter(self, path: Path, chapter_index: int, *, ctx: Context) -> ChapterContent:
        # Lands in Tasks 12 + 13.
        del path, chapter_index, ctx
        raise NotImplementedError("extract_chapter lands in Tasks 12 + 13")
