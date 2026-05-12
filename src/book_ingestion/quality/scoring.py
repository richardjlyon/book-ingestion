"""Map numeric Docling scores into our categorical Confidence grade.

Thresholds match Docling's own grade boundaries closely. See:
https://docling-project.github.io/docling/concepts/confidence_scores/
"""
from __future__ import annotations

from book_ingestion.ir import Confidence

_EXCELLENT = 0.90
_GOOD = 0.75
_FAIR = 0.50


def grade_from_score(score: float) -> Confidence:
    """Convert a Docling score in [0, 1] to a Confidence grade."""
    if score >= _EXCELLENT:
        return Confidence.EXCELLENT
    if score >= _GOOD:
        return Confidence.GOOD
    if score >= _FAIR:
        return Confidence.FAIR
    return Confidence.POOR
