"""Backend Protocol and shared Context.

Each backend (pdf, epub, pdf_ocr) implements `Backend`. `api.py` dispatches to
the right one based on `detect.detect_format()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from book_ingestion.cache import Cache
from book_ingestion.ir import BookSurvey, ChapterContent


@dataclass(frozen=True)
class Context:
    """Per-call execution context passed to backends."""
    cache: Cache
    use_cache: bool = True
    llm_assist: bool = False


class Backend(Protocol):
    """The interface every backend implements."""

    name: str

    def survey(self, path: Path, *, ctx: Context) -> BookSurvey: ...

    def extract_chapter(self, path: Path, chapter_index: int, *, ctx: Context) -> ChapterContent: ...
