"""Cross-format symmetry: PDF and EPUB surveys obey the same IR contract."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion import survey
from book_ingestion.ir import Provenance
from book_ingestion.quality.flags import KNOWN_FLAGS


@pytest.fixture
def synthetic_epub(tmp_path: Path) -> Path:
    from tests.fixtures.epub import build_epub_with_chapters
    return build_epub_with_chapters(tmp_path / "sym.epub")


@pytest.mark.slow
def test_survey_schema_uniform_across_formats(
    synthetic_pdf: Path, synthetic_epub: Path, tmp_cache_dir: Path
) -> None:
    """Both PDF and EPUB surveys must produce BookSurvey payloads obeying the
    same schema contract — same kind, same schema_version, valid map.provenance,
    flags from the closed vocabulary, source.format stamped per format.
    """
    pdf_survey = survey(synthetic_pdf, cache_dir=tmp_cache_dir)
    epub_survey = survey(synthetic_epub, cache_dir=tmp_cache_dir)

    # Same kind + schema version
    assert pdf_survey.kind == epub_survey.kind == "book_survey"
    assert pdf_survey.schema_version == epub_survey.schema_version

    # Both have a non-empty chapters list (synthetic fixtures both have content)
    assert pdf_survey.chapters
    assert epub_survey.chapters

    # Both have a closed-vocab provenance
    assert pdf_survey.map.provenance in set(Provenance)
    assert epub_survey.map.provenance in set(Provenance)

    # Every flag emitted by either format is in the closed vocabulary
    for flag in pdf_survey.quality.flags:
        assert flag in KNOWN_FLAGS, f"PDF emitted unknown flag: {flag!r}"
    for flag in epub_survey.quality.flags:
        assert flag in KNOWN_FLAGS, f"EPUB emitted unknown flag: {flag!r}"

    # Source.format is correctly stamped
    assert pdf_survey.source.format == "pdf"
    assert epub_survey.source.format == "epub"
