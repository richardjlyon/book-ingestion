"""Public API surface.

`survey()` and `extract_chapter()` are the only library entry points. Both
are deterministic given the same input and cache state.
"""
from __future__ import annotations

from pathlib import Path

from book_ingestion.backends.base import Backend, Context
from book_ingestion.cache import Cache
from book_ingestion.detect import detect_format
from book_ingestion.extractors.base import MetadataExtractor
from book_ingestion.extractors.epub import EpubMetadataExtractor
from book_ingestion.extractors.pdf import PdfMetadataExtractor
from book_ingestion.ir import BookSurvey, ChapterContent
from book_ingestion.metadata import BookMetadata

# Extractors are lightweight — eager construction is fine.
_EXTRACTORS: dict[str, MetadataExtractor] = {
    "pdf": PdfMetadataExtractor(),
    "epub": EpubMetadataExtractor(),
}

# Backends are heavy (Docling) — lazy-initialise on first use.
_BACKENDS: dict[str, Backend] = {}


def _backend_for(path: Path) -> Backend:
    fmt = detect_format(path)
    if fmt == "pdf":
        if "pdf" not in _BACKENDS:
            from book_ingestion.backends.pdf_docling import PdfDoclingBackend
            _BACKENDS["pdf"] = PdfDoclingBackend()
        return _BACKENDS["pdf"]
    raise ValueError(f"no backend registered for format: {fmt}")


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


def extract_metadata(path: Path, *, pages: int = 6) -> BookMetadata:
    """Extract frontmatter-shaped metadata from a book file.

    See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §3.
    """
    fmt = detect_format(path)
    if fmt not in _EXTRACTORS:
        raise ValueError(f"no metadata extractor registered for format: {fmt}")
    return _EXTRACTORS[fmt].extract_metadata(path, pages=pages)
