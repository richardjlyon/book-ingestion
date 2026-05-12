"""Intermediate representation models for book ingestion.

All payloads serialize to JSON via `.model_dump(mode='json')`. Every payload
carries a `schema_version` at the root; consumers must check it before parsing.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.1"


class Provenance(StrEnum):
    EMBEDDED = "embedded"
    INFERRED = "inferred"
    LLM_ASSISTED = "llm_assisted"
    NONE = "none"


class Confidence(StrEnum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


# ---- Locators -----------------------------------------------------------

class PageRange(BaseModel):
    """PDF locator: an inclusive page range."""
    model_config = ConfigDict(frozen=True)
    kind: Literal["page_range"] = "page_range"
    start_page: int
    end_page: int
    start_page_label: str | None = None
    end_page_label: str | None = None


class SpineRange(BaseModel):
    """EPUB locator (v2): a range across spine items."""
    model_config = ConfigDict(frozen=True)
    kind: Literal["spine_range"] = "spine_range"
    start_spine: int
    end_spine: int
    start_frag: str | None = None
    end_frag: str | None = None


Locator = Annotated[PageRange | SpineRange, Field(discriminator="kind")]


# ---- Source and survey --------------------------------------------------

class Source(BaseModel):
    model_config = ConfigDict(frozen=True)
    path: str
    sha256: str
    size_bytes: int
    format: Literal["pdf", "epub"]


class Chapter(BaseModel):
    model_config = ConfigDict(frozen=True)
    index: int
    title: str
    locator: Locator
    provenance: Provenance
    confidence: Confidence


class MapInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    provenance: Provenance
    confidence: Confidence
    method: str  # short tag: "pdf_outline" | "typographic" | "llm_assist" | "none"


class Quality(BaseModel):
    backend: str
    docling_mean_grade: Confidence | None = None
    docling_low_grade: Confidence | None = None
    pages_total: int | None = None
    pages_with_extraction_failures: int = 0
    pages_processed: list[int] = Field(default_factory=list)
    pages_with_failures: list[int] = Field(default_factory=list)
    block_confidence_counts: dict[str, int] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)


# ---- Blocks (simple_view) -----------------------------------------------

class Paragraph(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["paragraph"] = "paragraph"
    text: str
    page: int | None = None
    page_label: str | None = None
    confidence: Confidence
    footnote_refs: list[str] = Field(default_factory=list)
    list_marker: str | None = None
    continued_from: str | None = None


class Heading(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["heading"] = "heading"
    text: str
    level: int = Field(ge=1, le=6)
    page: int | None = None
    page_label: str | None = None
    confidence: Confidence


class Table(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["table"] = "table"
    page: int | None = None
    page_label: str | None = None
    confidence: Confidence
    rows: list[list[str]] | None = None
    raw_text: str


class FigureCaption(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["figure_caption"] = "figure_caption"
    text: str
    page: int | None = None
    page_label: str | None = None
    confidence: Confidence


class Footnote(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["footnote"] = "footnote"
    id: str
    text: str
    page: int | None = None
    page_label: str | None = None
    confidence: Confidence


class PageBreak(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["page_break"] = "page_break"
    page: int
    page_label: str | None = None


class FailedRegion(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["failed_region"] = "failed_region"
    page: int | None = None
    page_label: str | None = None
    reason: str
    raw_text: str | None = None


Block = Annotated[
    Paragraph | Heading | Table | FigureCaption | Footnote | PageBreak | FailedRegion,
    Field(discriminator="type"),
]


# ---- Top-level payloads -------------------------------------------------

class BookSurvey(BaseModel):
    schema_version: str
    kind: Literal["book_survey"] = "book_survey"
    source: Source
    metadata: dict[str, Any] = Field(default_factory=dict)
    chapters: list[Chapter] = Field(default_factory=list)
    map: MapInfo
    quality: Quality
    cache_paths: dict[str, str] = Field(default_factory=dict)
    page_labels: dict[int, str] = Field(default_factory=dict)
    page_label_provenance: Provenance = Provenance.NONE


class ChapterContent(BaseModel):
    schema_version: str
    kind: Literal["chapter_content"] = "chapter_content"
    source: Source
    chapter: Chapter
    simple_view: list[Block] = Field(default_factory=list)
    quality: Quality
    docling_document: None = None  # always null inline; see cache_paths
    cache_paths: dict[str, str] = Field(default_factory=dict)
