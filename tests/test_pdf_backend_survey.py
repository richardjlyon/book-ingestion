"""Tests for the PDF backend's survey() path."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion.backends.base import Context
from book_ingestion.backends.pdf_docling import PdfDoclingBackend
from book_ingestion.cache import Cache


@pytest.mark.slow
def test_survey_synthetic_pdf_runs_end_to_end(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    """survey() on the 1-page synthetic PDF returns a valid BookSurvey."""
    backend = PdfDoclingBackend()
    ctx = Context(cache=Cache(root=tmp_cache_dir))
    survey = backend.survey(synthetic_pdf, ctx=ctx)

    assert len(survey.source.sha256) == 64
    assert survey.quality.backend == "docling_pdf"
    assert survey.map.provenance.value in {"embedded", "inferred", "none"}
    docling_path = Path(survey.cache_paths["docling_document"])
    assert docling_path.exists()


@pytest.mark.slow
def test_survey_cache_hit_does_not_re_run_docling(
    synthetic_pdf: Path, tmp_cache_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second call with the same cache hits cache and skips Docling."""
    backend = PdfDoclingBackend()
    ctx = Context(cache=Cache(root=tmp_cache_dir))
    backend.survey(synthetic_pdf, ctx=ctx)

    calls = {"n": 0}

    def _boom(*_a: object, **_k: object) -> None:
        calls["n"] += 1
        raise RuntimeError("docling must not be called on cache hit")

    monkeypatch.setattr(backend, "_run_docling", _boom)
    backend.survey(synthetic_pdf, ctx=ctx)
    assert calls["n"] == 0
