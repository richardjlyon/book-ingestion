"""The v1 PDF backend, driven end-to-end by Docling."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from book_ingestion.backends.base import Context
from book_ingestion.ir import (
    SCHEMA_VERSION,
    BookSurvey,
    Chapter,
    ChapterContent,
    Confidence,
    PageRange,
    Provenance,
    Quality,
    Source,
)
from book_ingestion.page_labels import (
    infer_page_labels_from_blocks,
    read_pdf_page_labels,
)
from book_ingestion.projection.to_simple_view import (
    DoclingItem,
    ItemKind,
    project_to_simple_view,
)
from book_ingestion.quality.flags import validate_flag
from book_ingestion.quality.scoring import grade_from_score
from book_ingestion.structure.embedded_toc import HeadingHint, build_chapter_map

logger = logging.getLogger(__name__)


class PdfDoclingBackend:
    """PDF backend. Survey + extract via Docling's DocumentConverter."""

    name = "docling_pdf"

    def survey(self, path: Path, *, ctx: Context) -> BookSurvey:
        if ctx.use_cache:
            cached = ctx.cache.read(path, "survey.json")
            if cached is not None:
                return BookSurvey.model_validate(cached)

        docling_dict = self._get_or_run_docling(path, ctx=ctx)
        survey = self._build_survey(path, docling_dict, ctx=ctx)
        ctx.cache.write(path, "survey.json", survey.model_dump(mode="json"))
        return survey

    def _get_or_run_docling(self, path: Path, *, ctx: Context) -> dict[str, Any]:
        if ctx.use_cache:
            cached = ctx.cache.read(path, "docling.json")
            if cached is not None:
                logger.info("docling cache hit for %s", path)
                return cached  # type: ignore[no-any-return]
        return self._run_docling(path, ctx=ctx)

    def _run_docling(self, path: Path, *, ctx: Context) -> dict[str, Any]:
        """Run Docling on the file and persist its serialized output."""
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        logger.info("running docling on %s", path)
        result = converter.convert(str(path))

        doc_dict = result.document.export_to_dict()
        confidence = self._extract_confidence(result)
        page_count = self._page_count(result)

        payload = {
            "document": doc_dict,
            "confidence": confidence,
            "page_count": page_count,
        }
        ctx.cache.write(path, "docling.json", payload)
        return payload

    @staticmethod
    def _extract_confidence(result: Any) -> dict[str, Any]:
        conf = getattr(result, "confidence", None)
        if conf is None:
            return {"mean_grade": None, "low_grade": None, "scores": {}}
        return {
            "mean_grade": getattr(conf, "mean_grade", None),
            "low_grade": getattr(conf, "low_grade", None),
            "scores": {
                "parse": getattr(conf, "parse_score", None),
                "layout": getattr(conf, "layout_score", None),
                "ocr": getattr(conf, "ocr_score", None),
                "table": getattr(conf, "table_score", None),
            },
        }

    @staticmethod
    def _page_count(result: Any) -> int:
        pages = getattr(result, "pages", None) or []
        return len(pages) or 0

    def _build_survey(self, path: Path, docling: dict[str, Any], *, ctx: Context) -> BookSurvey:
        from book_ingestion.cache import sha256_of_file

        hints = self._extract_heading_hints(docling["document"])
        chapters, map_info = build_chapter_map(hints, total_pages=docling["page_count"] or 1)

        flags: list[str] = []
        if map_info.provenance.value == "embedded":
            flags.append("embedded_toc_present")
        elif map_info.provenance.value == "none":
            flags.append("toc_unresolved")

        # Page labels: try /PageLabels first (exact); fall back to heuristic inference.
        labels: dict[int, str] | None = read_pdf_page_labels(path)
        page_label_provenance = Provenance.NONE
        if labels:
            page_label_provenance = Provenance.EMBEDDED
            flags.append("page_labels_embedded")
        else:
            # Build per-page text snapshot from the texts array for inference.
            page_snapshot: dict[int, list[str]] = {}
            for entry in docling["document"].get("texts") or []:
                if not isinstance(entry, dict):
                    continue
                try:
                    prov = entry.get("prov") or []
                    if not prov or not isinstance(prov[0], dict) or "page_no" not in prov[0]:
                        continue
                    page = int(prov[0]["page_no"])
                    text = str(entry.get("text") or "").strip()
                    if text:
                        page_snapshot.setdefault(page, []).append(text)
                except (TypeError, ValueError, KeyError):
                    continue
            labels = infer_page_labels_from_blocks(page_snapshot)
            if labels:
                page_label_provenance = Provenance.INFERRED
                flags.append("page_labels_inferred")
            else:
                flags.append("page_labels_unresolved")

        for f in flags:
            validate_flag(f)

        conf = docling["confidence"]
        mean_grade = self._grade_field(conf.get("mean_grade"))
        low_grade = self._grade_field(conf.get("low_grade"))

        return BookSurvey(
            schema_version=SCHEMA_VERSION,
            source=Source(
                path=str(path.resolve()),
                sha256=sha256_of_file(path),
                size_bytes=path.stat().st_size,
                format="pdf",
            ),
            metadata=self._extract_metadata(docling["document"]),
            chapters=self._stamp_chapter_labels(chapters, labels or {}),
            map=map_info,
            quality=Quality(
                backend=self.name,
                docling_mean_grade=mean_grade,
                docling_low_grade=low_grade,
                pages_total=docling["page_count"],
                flags=flags,
            ),
            cache_paths={"docling_document": str(ctx.cache.dir_for(path) / "docling.json")},
            page_labels=labels or {},
            page_label_provenance=page_label_provenance,
        )

    @staticmethod
    def _grade_field(raw: Any) -> Confidence | None:
        if raw is None:
            return None
        if isinstance(raw, str):
            for c in Confidence:
                if raw == c.value:
                    return c
            return None
        if isinstance(raw, int | float):
            return grade_from_score(float(raw))
        for attr in ("name", "value"):
            v = getattr(raw, attr, None)
            if isinstance(v, str):
                for c in Confidence:
                    if v == c.value:
                        return c
        return None

    @staticmethod
    def _extract_metadata(doc_dict: dict[str, Any]) -> dict[str, Any]:
        md = (doc_dict.get("origin") or {}) if isinstance(doc_dict.get("origin"), dict) else {}
        return {
            "title": md.get("filename") or doc_dict.get("name") or None,
            "authors": [],
            "publisher": None,
            "year": None,
            "isbn": None,
            "language": None,
        }

    @staticmethod
    def _stamp_chapter_labels(
        chapters: list[Chapter], labels: dict[int, str]
    ) -> list[Chapter]:
        """Return chapters with start/end_page_label populated from `labels` when known."""
        stamped: list[Chapter] = []
        for c in chapters:
            if not isinstance(c.locator, PageRange):
                stamped.append(c)
                continue
            new_locator = c.locator.model_copy(update={
                "start_page_label": labels.get(c.locator.start_page),
                "end_page_label": labels.get(c.locator.end_page),
            })
            stamped.append(c.model_copy(update={"locator": new_locator}))
        return stamped

    @staticmethod
    def _extract_heading_hints(doc_dict: dict[str, Any]) -> list[HeadingHint]:
        hints: list[HeadingHint] = []
        texts = doc_dict.get("texts") or []
        for item in texts:
            if not isinstance(item, dict):
                continue
            try:
                label = str(item.get("label") or "").lower()
                if "section_header" not in label and "heading" not in label:
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                prov = item.get("prov") or []
                page = int(prov[0]["page_no"]) if prov and isinstance(prov[0], dict) and "page_no" in prov[0] else 1
                level = int(item.get("level") or 1)
                hints.append(HeadingHint(text=text, level=level, page=page))
            except (TypeError, ValueError, KeyError):
                continue
        return hints

    # --- extract ----------------------------------------------------------

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
        docling_payload = self._get_or_run_docling(path, ctx=ctx)
        assert isinstance(chapter.locator, PageRange)
        items = self._slice_to_items(docling_payload["document"], chapter.locator)
        blocks = project_to_simple_view(items, page_labels=survey.page_labels or None)

        pages_processed = list(range(chapter.locator.start_page, chapter.locator.end_page + 1))
        pages_with_failures = sorted({b.page for b in blocks if b.type == "failed_region" and b.page is not None})
        counts: dict[str, int] = {}
        for b in blocks:
            if hasattr(b, "confidence"):
                key = getattr(b, "confidence").value  # noqa: B009
                counts[key] = counts.get(key, 0) + 1

        chapter_path = self._write_chapter_slice(path, ctx=ctx, chapter_index=chapter_index, locator=chapter.locator)

        content = ChapterContent(
            schema_version=SCHEMA_VERSION,
            source=survey.source,
            chapter=chapter,
            simple_view=blocks,
            quality=Quality(
                backend=self.name,
                pages_processed=pages_processed,
                pages_with_failures=pages_with_failures,
                block_confidence_counts=counts,
                flags=[],
            ),
            cache_paths={"docling_chapter": str(chapter_path)},
        )
        ctx.cache.write(path, f"chapter-{chapter_index}.json", content.model_dump(mode="json"))
        return content

    @staticmethod
    def _slice_to_items(doc_dict: dict[str, Any], locator: PageRange) -> list[DoclingItem]:
        items: list[DoclingItem] = []
        for entry in doc_dict.get("texts") or []:
            if not isinstance(entry, dict):
                continue
            try:
                prov = entry.get("prov") or []
                page = int(prov[0]["page_no"]) if prov and isinstance(prov[0], dict) and "page_no" in prov[0] else 0
                if page < locator.start_page or page > locator.end_page:
                    continue
                label = str(entry.get("label") or "").lower()
                text = str(entry.get("text") or "")
                score = float(entry.get("confidence") or 0.95)
                kind: ItemKind
                extra: dict[str, Any] = {}
                if "section_header" in label or "heading" in label:
                    kind = "heading"
                    extra["level"] = int(entry.get("level") or 1)
                elif "list_item" in label:
                    kind = "list_item"
                    extra["list_marker"] = entry.get("marker")
                elif "footnote" in label:
                    kind = "footnote"
                    extra["fn_id"] = entry.get("self_ref") or f"fn-{len(items)}"
                elif "caption" in label:
                    kind = "figure_caption"
                else:
                    kind = "paragraph"
                items.append(DoclingItem(kind=kind, text=text, page=page, score=score, extra=extra))
            except (TypeError, ValueError, KeyError, AttributeError):
                continue

        for entry in doc_dict.get("tables") or []:
            if not isinstance(entry, dict):
                continue
            try:
                prov = entry.get("prov") or []
                page = int(prov[0]["page_no"]) if prov and isinstance(prov[0], dict) and "page_no" in prov[0] else 0
                if page < locator.start_page or page > locator.end_page:
                    continue
                rows = _table_rows_from_docling(entry)
                raw_text = "\n".join(" | ".join(r) for r in rows) if rows else ""
                score = float(entry.get("confidence") or 0.80)
                items.append(
                    DoclingItem(
                        kind="table",
                        text="",
                        page=page,
                        score=score,
                        extra={"rows": rows, "raw_text": raw_text},
                    )
                )
            except (TypeError, ValueError, KeyError, AttributeError):
                continue

        items.sort(key=lambda it: it.page)
        return items

    def _write_chapter_slice(
        self,
        path: Path,
        *,
        ctx: Context,
        chapter_index: int,
        locator: PageRange,
    ) -> Path:
        payload = {
            "chapter_index": chapter_index,
            "start_page": locator.start_page,
            "end_page": locator.end_page,
        }
        return ctx.cache.write(path, f"chapter-{chapter_index}.docling.json", payload)


def _table_rows_from_docling(table_entry: dict[str, Any]) -> list[list[str]]:
    """Pull a 2D list of strings from a DoclingDocument table entry."""
    data = table_entry.get("data") or {}
    grid = data.get("grid") or []
    rows: list[list[str]] = []
    for row in grid:
        rows.append([str(cell.get("text") or "") for cell in row])
    return rows
