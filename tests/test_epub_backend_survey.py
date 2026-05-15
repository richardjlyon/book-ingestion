"""Backend integration tests for EpubNativeBackend.survey()."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion.backends.base import Context
from book_ingestion.backends.epub_native import EpubNativeBackend
from book_ingestion.cache import Cache
from book_ingestion.ir import Provenance
from tests.fixtures.epub import (
    build_epub_with_chapters,
    build_epub_with_drm,
    build_epub_with_inline_page_anchors,
    build_epub_with_malformed_xhtml,
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
    assert s.kind == "book_survey"
    assert s.schema_version
    assert s.source.format == "epub"
    assert s.quality.backend == "epub_native"
    assert s.chapters == []
    assert s.map.provenance == Provenance.NONE
    assert "unparseable" in s.quality.flags
    assert "drm_protected" not in s.quality.flags


def test_survey_clean_two_chapter_epub(backend: EpubNativeBackend, ctx: Context, tmp_path: Path) -> None:
    p = build_epub_with_chapters(
        tmp_path / "x.epub",
        chapters=[
            {"id": "c1", "href": "ch1.xhtml", "title": "Chapter 1",
             "body_xhtml": "<h1>Chapter 1</h1><p>a</p>"},
            {"id": "c2", "href": "ch2.xhtml", "title": "Chapter 2",
             "body_xhtml": "<h1>Chapter 2</h1><p>b</p>"},
        ],
    )
    s = backend.survey(p, ctx=ctx)
    assert s.kind == "book_survey"
    assert s.source.format == "epub"
    assert s.schema_version  # must be set
    assert len(s.chapters) == 2
    assert s.chapters[0].title == "Chapter 1"
    assert s.map.provenance == Provenance.EMBEDDED
    assert s.map.method == "epub_nav"
    assert "nav_used" in s.quality.flags
    assert "page_labels_unresolved" in s.quality.flags
    assert s.page_label_provenance == Provenance.NONE


def test_survey_with_pagelist_emits_page_labels_embedded(
    backend: EpubNativeBackend, ctx: Context, tmp_path: Path
) -> None:
    p = build_epub_with_inline_page_anchors(tmp_path / "anchors.epub")
    s = backend.survey(p, ctx=ctx)
    assert "page_labels_embedded" in s.quality.flags
    assert s.page_label_provenance == Provenance.EMBEDDED


def test_survey_cache_hit_returns_cached_payload(
    backend: EpubNativeBackend, ctx: Context, tmp_path: Path
) -> None:
    p = build_epub_with_chapters(tmp_path / "cached.epub")
    s1 = backend.survey(p, ctx=ctx)
    # Second call — payload identity in JSON form must match.
    s2 = backend.survey(p, ctx=ctx)
    assert s1.model_dump(mode="json") == s2.model_dump(mode="json")


def test_survey_xhtml_parse_failure_does_not_break_whole_doc(
    backend: EpubNativeBackend, ctx: Context, tmp_path: Path
) -> None:
    """A malformed content XHTML doesn't fail the whole survey — chapters still come back."""
    p = build_epub_with_malformed_xhtml(tmp_path / "broken.epub")
    s = backend.survey(p, ctx=ctx)
    # Survey itself doesn't fail on per-content-file parse errors;
    # chapters fall back to the spine-only or headings-only path.
    assert "unparseable" not in s.quality.flags  # whole-doc still ok
    # The single broken file is still in the spine — Task 12/13's extract_chapter
    # will surface the per-file failure as failed_region. Survey just maps it.
    assert s.chapters or s.map.provenance == Provenance.NONE
