"""Vocabulary of quality flags.

Every value emitted into `BookSurvey.quality.flags` or `ChapterContent.quality.flags`
must be in `KNOWN_FLAGS`. This keeps the vocabulary documented in one place and
prevents drift in what downstream consumers must understand.
"""
from __future__ import annotations

KNOWN_FLAGS: frozenset[str] = frozenset(
    {
        # OCR
        "ocr_used",
        "ocr_low_confidence_block",
        "ocr_severely_degraded",
        # Layout
        "two_column_layout",
        "mixed_layout",
        # Structure / TOC
        "embedded_toc_present",
        "toc_inferred",
        "toc_unresolved",
        # Tables
        "tables_present",
        "table_structure_uncertain",
        # Text quality
        "unicode_normalization_failure",
        # Tool state
        "llm_assist_used",
        # Whole-document refusal
        "unparseable",
        # Page labels
        "page_labels_embedded",
        "page_labels_inferred",
        "page_labels_unresolved",
    }
)


def validate_flag(flag: str) -> None:
    """Raise ValueError if `flag` is not in `KNOWN_FLAGS`.

    Use this at every emission site to keep the vocabulary stable.
    """
    if flag not in KNOWN_FLAGS:
        raise ValueError(
            f"unknown quality flag: {flag!r}. Add it to KNOWN_FLAGS with a comment."
        )
