"""Public API surface.

`survey()` and `extract_chapter()` are the only library entry points. Both
are deterministic given the same input and cache state.
"""
from __future__ import annotations

from pathlib import Path

from book_ingestion.backends.base import Backend, Context
from book_ingestion.backends.pdf_docling import PdfDoclingBackend
from book_ingestion.cache import Cache
from book_ingestion.detect import detect_format
from book_ingestion.ir import BookSurvey, ChapterContent

_BACKENDS: dict[str, Backend] = {
    "pdf": PdfDoclingBackend(),
    # "epub": EpubBackend(),     # M2
    # "pdf_ocr": OcrBackend(),   # M3
}


def _backend_for(path: Path) -> Backend:
    fmt = detect_format(path)
    if fmt not in _BACKENDS:
        raise ValueError(f"no backend registered for format: {fmt}")
    return _BACKENDS[fmt]


def survey(
    path: Path,
    *,
    cache_dir: Path | None = None,
    use_cache: bool = True,
    llm_assist: bool = False,
) -> BookSurvey:
    """Produce a BookSurvey for `path`. See spec §3.1."""
    backend = _backend_for(path)
    ctx = Context(cache=Cache(root=cache_dir), use_cache=use_cache, llm_assist=llm_assist)
    return backend.survey(path, ctx=ctx)


def extract_chapter(
    path: Path,
    chapter_index: int,
    *,
    cache_dir: Path | None = None,
    use_cache: bool = True,
) -> ChapterContent:
    """Produce a ChapterContent for chapter `chapter_index` of `path`. See spec §3.2."""
    backend = _backend_for(path)
    ctx = Context(cache=Cache(root=cache_dir), use_cache=use_cache)
    return backend.extract_chapter(path, chapter_index, ctx=ctx)
