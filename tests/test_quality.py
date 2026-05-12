"""Tests for quality scoring and flags."""
from __future__ import annotations

import pytest

from book_ingestion.ir import Confidence
from book_ingestion.quality.flags import KNOWN_FLAGS, validate_flag
from book_ingestion.quality.scoring import grade_from_score


@pytest.mark.parametrize(
    ("score", "grade"),
    [
        (0.95, Confidence.EXCELLENT),
        (0.80, Confidence.GOOD),
        (0.60, Confidence.FAIR),
        (0.30, Confidence.POOR),
        (0.0, Confidence.POOR),
    ],
)
def test_grade_from_score(score: float, grade: Confidence) -> None:
    assert grade_from_score(score) == grade


def test_known_flags_contains_expected() -> None:
    expected = {
        "ocr_used",
        "ocr_low_confidence_block",
        "ocr_severely_degraded",
        "two_column_layout",
        "mixed_layout",
        "embedded_toc_present",
        "toc_inferred",
        "toc_unresolved",
        "tables_present",
        "table_structure_uncertain",
        "unicode_normalization_failure",
        "llm_assist_used",
        "unparseable",
    }
    assert expected <= KNOWN_FLAGS


def test_validate_flag_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown quality flag"):
        validate_flag("totally_made_up_flag")


def test_validate_flag_accepts_known() -> None:
    validate_flag("ocr_used")
