"""The v1 PDF backend, driven end-to-end by Docling."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from book_ingestion.backends.base import Context
from book_ingestion.ir import (
    SCHEMA_VERSION,
    BookSurvey,
    Confidence,
    Quality,
    Source,
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
            chapters=chapters,
            map=map_info,
            quality=Quality(
                backend=self.name,
                docling_mean_grade=mean_grade,
                docling_low_grade=low_grade,
                pages_total=docling["page_count"],
                flags=flags,
            ),
            cache_paths={"docling_document": str(ctx.cache.dir_for(path) / "docling.json")},
        )

    @staticmethod
    def _grade_field(raw: Any) -> Confidence | None:
        if raw is None:
            return None
        if isinstance(raw, str):
            for c in Confidence:
                if raw == c.value:
                    return c
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
    def _extract_heading_hints(doc_dict: dict[str, Any]) -> list[HeadingHint]:
        hints: list[HeadingHint] = []
        texts = doc_dict.get("texts") or []
        for item in texts:
            label = str(item.get("label") or "").lower()
            if "section_header" not in label and "heading" not in label:
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            prov = item.get("prov") or []
            page = int(prov[0]["page_no"]) if prov and "page_no" in prov[0] else 1
            level = int(item.get("level") or 1)
            hints.append(HeadingHint(text=text, level=level, page=page))
        return hints
