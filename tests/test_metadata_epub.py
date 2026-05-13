"""Tests for EpubMetadataExtractor + supporting EPUB fixture helpers."""
from __future__ import annotations

from pathlib import Path

from tests.fixtures.epub import (
    build_epub,
    build_epub_with_drm,
    build_epub_with_truncated_title,
    build_malformed_epub,
)


def test_epub_fixture_basic_builds(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "basic.epub",
        dc_title="Sample Book",
        creators=[("Smith, Jane", "aut")],
        isbn="9781234567897",
        publisher="Example Press",
        language="en",
    )
    assert p.exists() and p.stat().st_size > 500


def test_epub_fixture_truncated_title_builds(tmp_path: Path) -> None:
    p = build_epub_with_truncated_title(
        tmp_path / "trunc.epub",
        dc_title="Gaza",
        full_title_in_xhtml="Gaza: An Inquest Into Its Martyrdom",
    )
    assert p.exists()


def test_epub_fixture_drm_builds(tmp_path: Path) -> None:
    p = build_epub_with_drm(tmp_path / "drm.epub")
    assert p.exists()


def test_epub_fixture_malformed_builds(tmp_path: Path) -> None:
    p = build_malformed_epub(tmp_path / "bad.epub")
    assert p.exists()
