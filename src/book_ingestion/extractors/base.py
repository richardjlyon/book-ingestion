"""MetadataExtractor Protocol — see docs/superpowers/specs/2026-05-13-extract-metadata-design.md §2.

Each format gets one extractor. Backends remain separate (in `backends/`)
and are used for the heavyweight IR path; metadata extractors are
lightweight, no caching, no Docling.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from book_ingestion.metadata import BookMetadata


class MetadataExtractor(Protocol):
    """The interface every metadata extractor implements."""

    name: str

    def extract_metadata(self, path: Path, *, pages: int = 6) -> BookMetadata: ...
