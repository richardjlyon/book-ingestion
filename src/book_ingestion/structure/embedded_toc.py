"""Build a chapter map from a flat list of heading hints.

The PDF backend extracts heading hints from Docling's section structure and
hands them here. Keeping this function independent of Docling makes it unit-
testable without spinning the engine up.
"""
from __future__ import annotations

from dataclasses import dataclass

from book_ingestion.ir import (
    Chapter,
    Confidence,
    MapInfo,
    PageRange,
    Provenance,
)


@dataclass(frozen=True)
class HeadingHint:
    """A heading observed somewhere in the document, with its page."""
    text: str
    level: int
    page: int


def build_chapter_map(
    hints: list[HeadingHint],
    *,
    total_pages: int,
    provenance: Provenance = Provenance.EMBEDDED,
    method: str = "pdf_outline",
) -> tuple[list[Chapter], MapInfo]:
    """Turn heading hints into a list of Chapters + a MapInfo summary.

    Only level==1 hints are treated as chapter boundaries. Each chapter spans
    from its own page to (the next chapter's page - 1), or to total_pages for
    the last chapter.

    Returns ([], MapInfo(provenance=NONE, ...)) when no level-1 hints exist.
    """
    top_level = [h for h in hints if h.level == 1]
    if not top_level:
        return [], MapInfo(provenance=Provenance.NONE, confidence=Confidence.POOR, method="none")

    chapters: list[Chapter] = []
    for i, h in enumerate(top_level):
        # Guard against consecutive hints on the same (or earlier) page, which can
        # happen when a PDF outline has cover-page titles that share a page with
        # the real chapter heading. Clamp to a 1-page range minimum.
        if i + 1 < len(top_level):
            end = max(h.page, top_level[i + 1].page - 1)
        else:
            end = max(h.page, total_pages)
        chapters.append(
            Chapter(
                index=i,
                title=h.text,
                locator=PageRange(start_page=h.page, end_page=end),
                provenance=provenance,
                confidence=Confidence.EXCELLENT if provenance == Provenance.EMBEDDED else Confidence.FAIR,
            )
        )

    map_conf = Confidence.GOOD if provenance == Provenance.EMBEDDED else Confidence.FAIR
    return chapters, MapInfo(provenance=provenance, confidence=map_conf, method=method)
