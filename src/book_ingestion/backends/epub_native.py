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
    Block,
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
        from book_ingestion.extractors._epub_common import read_pageList_anchors
        from book_ingestion.structure.epub_chapters import (
            build_chapter_map_epub,
            extract_spine,
            parse_nav_or_ncx,
        )

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

                opf_dir = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""

                spine = extract_spine(opf_root, opf_dir=opf_dir)
                nav = parse_nav_or_ncx(zf, opf_dir=opf_dir)
                chapters, map_info, recipe_flags = build_chapter_map_epub(
                    spine=spine, nav=nav, zf=zf, opf_dir=opf_dir, opf_root=opf_root,
                )
                page_label_map = read_pageList_anchors(opf_root, zf, names, opf_dir=opf_dir)

                flags = set(recipe_flags)
                if page_label_map:
                    flags.add("page_labels_embedded")
                    page_label_provenance = Provenance.EMBEDDED
                else:
                    flags.add("page_labels_unresolved")
                    page_label_provenance = Provenance.NONE

                sorted_flags = sorted(flags)
                for f in sorted_flags:
                    validate_flag(f)

                # page_labels: dict[int, str] — only int-coercible values from the anchor map.
                # The full anchor map is consumed at extract time via read_pageList_anchors,
                # not threaded through the cache layer.
                page_labels_field: dict[int, str] = {}
                for v in page_label_map.values():
                    try:
                        page_labels_field[int(v)] = v
                    except ValueError:
                        continue

                return BookSurvey(
                    schema_version=SCHEMA_VERSION,
                    source=source,
                    metadata={},
                    chapters=chapters,
                    map=map_info,
                    quality=Quality(backend=self.name, flags=sorted_flags),
                    page_labels=page_labels_field,
                    page_label_provenance=page_label_provenance,
                )
        except Exception as exc:  # defensive — surface as degraded rather than crash CLI
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
        if ctx.use_cache:
            cached = ctx.cache.read(path, f"chapter-{chapter_index}.json")
            if cached is not None:
                return ChapterContent.model_validate(cached)

        survey = self.survey(path, ctx=ctx)
        if chapter_index < 0 or chapter_index >= len(survey.chapters):
            raise IndexError(
                f"chapter_index {chapter_index} out of range "
                f"(book has {len(survey.chapters)} chapters)"
            )
        chapter = survey.chapters[chapter_index]
        # SpineRange is the only valid locator for EPUB chapters.
        from book_ingestion.ir import SpineRange
        assert isinstance(chapter.locator, SpineRange)

        from book_ingestion.extractors._epub_common import read_pageList_anchors
        from book_ingestion.projection.epub_to_simple_view import project_xhtml_to_blocks
        from book_ingestion.structure.epub_chapters import extract_spine

        with open_epub_zip(path) as zf:
            opf_path = find_opf_path(zf)
            assert opf_path is not None
            opf_root = parse_opf_root(zf, opf_path)
            assert opf_root is not None
            opf_dir = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""
            spine = extract_spine(opf_root, opf_dir=opf_dir)
            page_label_map = read_pageList_anchors(
                opf_root, zf, set(zf.namelist()), opf_dir=opf_dir,
            )

            flags: set[str] = set()
            blocks: list[Block] = []

            # Multi-file + fragment-bounded extraction lands in Task 13.
            if (chapter.locator.start_spine != chapter.locator.end_spine
                    or chapter.locator.start_frag is not None
                    or chapter.locator.end_frag is not None):
                raise NotImplementedError("multi-spine + fragment extraction lands in Task 13")

            spine_idx = chapter.locator.start_spine
            spine_item = next((s for s in spine if s.idx == spine_idx), None)
            if spine_item is None:
                raise IndexError(f"spine index {spine_idx} not found in resolved spine")
            try:
                xhtml_bytes = zf.read(spine_item.href)
            except KeyError as exc:
                raise IndexError(f"content file {spine_item.href} missing from zip") from exc

            file_blocks = project_xhtml_to_blocks(
                xhtml_bytes=xhtml_bytes,
                spine_idx=spine_idx,
                page_label_map=page_label_map,
            )
            blocks.extend(file_blocks)
            if any(b.type == "failed_region" for b in file_blocks):
                flags.add("xhtml_parse_failure")

        for f in flags:
            validate_flag(f)

        counts: dict[str, int] = {}
        for b in blocks:
            if hasattr(b, "confidence"):
                key = b.confidence.value
                counts[key] = counts.get(key, 0) + 1

        content = ChapterContent(
            schema_version=SCHEMA_VERSION,
            source=survey.source,
            chapter=chapter,
            simple_view=blocks,
            quality=Quality(
                backend=self.name,
                pages_processed=[chapter.locator.start_spine],
                pages_with_failures=sorted({
                    b.page for b in blocks
                    if b.type == "failed_region" and b.page is not None
                }),
                block_confidence_counts=counts,
                flags=sorted(flags),
            ),
            cache_paths={},
        )
        ctx.cache.write(path, f"chapter-{chapter_index}.json", content.model_dump(mode="json"))
        return content
