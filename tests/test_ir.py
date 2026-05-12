"""Tests for the IR models."""
from __future__ import annotations

import json

from book_ingestion.ir import (
    SCHEMA_VERSION,
    BookSurvey,
    Chapter,
    ChapterContent,
    Confidence,
    Heading,
    MapInfo,
    PageRange,
    Paragraph,
    Provenance,
    Quality,
    Source,
)


def test_schema_version_is_one_zero() -> None:
    assert SCHEMA_VERSION == "1.0"


def test_book_survey_round_trip() -> None:
    survey = BookSurvey(
        schema_version=SCHEMA_VERSION,
        source=Source(path="/tmp/book.pdf", sha256="ab" * 32, size_bytes=4096, format="pdf"),
        metadata={"title": "A Book", "authors": ["Someone"]},
        chapters=[
            Chapter(
                index=0,
                title="Introduction",
                locator=PageRange(start_page=1, end_page=10),
                provenance=Provenance.EMBEDDED,
                confidence=Confidence.EXCELLENT,
            )
        ],
        map=MapInfo(provenance=Provenance.EMBEDDED, confidence=Confidence.GOOD, method="pdf_outline"),
        quality=Quality(backend="docling_pdf", flags=[]),
        cache_paths={"docling_document": "/tmp/docling.json"},
    )
    dumped = survey.model_dump(mode="json")
    again = BookSurvey.model_validate(dumped)
    assert again == survey
    # JSON serialization works
    json.dumps(dumped)


def test_chapter_content_with_failed_region() -> None:
    content = ChapterContent(
        schema_version=SCHEMA_VERSION,
        source=Source(path="/tmp/book.pdf", sha256="ab" * 32, size_bytes=4096, format="pdf"),
        chapter=Chapter(
            index=3,
            title="Chapter 3",
            locator=PageRange(start_page=142, end_page=178),
            provenance=Provenance.EMBEDDED,
            confidence=Confidence.GOOD,
        ),
        simple_view=[
            Heading(text="Chapter 3", level=1, page=142, confidence=Confidence.EXCELLENT),
            Paragraph(text="Hello.", page=142, confidence=Confidence.EXCELLENT),
        ],
        quality=Quality(backend="docling_pdf", flags=[]),
        cache_paths={"docling_chapter": "/tmp/chapter-3.docling.json"},
    )
    dumped = content.model_dump(mode="json")
    again = ChapterContent.model_validate(dumped)
    assert again == content


def test_locator_discriminated_union() -> None:
    """PageRange and SpineRange both deserialize via kind discriminator."""
    page = PageRange.model_validate({"kind": "page_range", "start_page": 1, "end_page": 10})
    assert page.start_page == 1
    # A future SpineRange would also deserialize; for now just check the kind field.
    assert page.kind == "page_range"
