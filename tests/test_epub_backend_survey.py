"""Backend integration tests for EpubNativeBackend.survey()."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion.backends.base import Context
from book_ingestion.backends.epub_native import EpubNativeBackend
from book_ingestion.cache import Cache
from book_ingestion.ir import Provenance
from tests.fixtures.epub import (
    build_epub_with_drm,
    build_malformed_epub,
)


@pytest.fixture
def backend() -> EpubNativeBackend:
    return EpubNativeBackend()


@pytest.fixture
def ctx(tmp_cache_dir: Path) -> Context:
    return Context(cache=Cache(root=tmp_cache_dir), use_cache=True)


def test_survey_drm_returns_degraded_payload(backend: EpubNativeBackend, ctx: Context, tmp_path: Path) -> None:
    p = build_epub_with_drm(tmp_path / "drm.epub")
    s = backend.survey(p, ctx=ctx)
    assert s.kind == "book_survey"
    assert s.source.format == "epub"
    assert s.chapters == []
    assert s.map.provenance == Provenance.NONE
    assert "unparseable" in s.quality.flags
    assert "drm_protected" in s.quality.flags
    assert s.quality.backend == "epub_native"


def test_survey_malformed_returns_degraded_payload(backend: EpubNativeBackend, ctx: Context, tmp_path: Path) -> None:
    p = build_malformed_epub(tmp_path / "malformed.epub")
    s = backend.survey(p, ctx=ctx)
    assert s.chapters == []
    assert s.map.provenance == Provenance.NONE
    assert "unparseable" in s.quality.flags
    assert "drm_protected" not in s.quality.flags
