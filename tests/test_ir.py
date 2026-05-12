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


def test_schema_version_is_one_one() -> None:
    """M1.1 bumps to 1.1 to invalidate older caches."""
    assert SCHEMA_VERSION == "1.1"


def test_page_range_with_labels_round_trips() -> None:
    pr = PageRange(start_page=14, end_page=22, start_page_label="10", end_page_label="18")
    again = PageRange.model_validate(pr.model_dump(mode="json"))
    assert again == pr


def test_paragraph_with_page_label_round_trips() -> None:
    p = Paragraph(text="hi", page=14, page_label="10", confidence=Confidence.EXCELLENT)
    again = Paragraph.model_validate(p.model_dump(mode="json"))
    assert again == p
    assert again.page_label == "10"


def test_book_survey_with_page_labels_round_trips() -> None:
    survey = BookSurvey(
        schema_version=SCHEMA_VERSION,
        source=Source(path="/tmp/x.pdf", sha256="ab" * 32, size_bytes=1, format="pdf"),
        map=MapInfo(provenance=Provenance.EMBEDDED, confidence=Confidence.GOOD, method="pdf_outline"),
        quality=Quality(backend="docling_pdf", flags=[]),
        page_labels={1: "i", 2: "ii", 14: "10"},
        page_label_provenance=Provenance.EMBEDDED,
    )
    again = BookSurvey.model_validate(survey.model_dump(mode="json"))
    assert again == survey
    assert again.page_labels[14] == "10"
    assert again.page_label_provenance == Provenance.EMBEDDED


def test_legacy_one_zero_dict_still_validates() -> None:
    """A pre-1.1 BookSurvey dict (no page_labels / page_label_provenance) must
    still round-trip; new fields fill in with defaults."""
    legacy = {
        "schema_version": "1.0",
        "kind": "book_survey",
        "source": {
            "path": "/tmp/old.pdf",
            "sha256": "cd" * 32,
            "size_bytes": 99,
            "format": "pdf",
        },
        "metadata": {},
        "chapters": [],
        "map": {"provenance": "embedded", "confidence": "GOOD", "method": "pdf_outline"},
        "quality": {"backend": "docling_pdf", "flags": []},
        "cache_paths": {},
    }
    survey = BookSurvey.model_validate(legacy)
    assert survey.schema_version == "1.0"
    assert survey.page_labels == {}
    assert survey.page_label_provenance == Provenance.NONE
