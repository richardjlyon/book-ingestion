"""Tests for the closed-vocabulary flag system."""
from __future__ import annotations

import pytest

from book_ingestion.quality.flags import KNOWN_FLAGS, validate_flag


@pytest.mark.parametrize(
    "flag",
    [
        "nav_used",
        "spine_only",
        "headings_split_used",
        "chapter_spans_multiple_files",
        "xhtml_parse_failure",
        "drm_protected",
    ],
)
def test_m21_flag_in_known_set(flag: str) -> None:
    assert flag in KNOWN_FLAGS, f"M2.1 flag {flag!r} missing from KNOWN_FLAGS"
    validate_flag(flag)  # must not raise


def test_unknown_flag_still_raises() -> None:
    with pytest.raises(ValueError, match="unknown quality flag"):
        validate_flag("not_a_real_flag")
