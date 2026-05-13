"""Tests for the BookMetadata Pydantic model and its sub-models."""
from __future__ import annotations


def test_imports() -> None:
    from book_ingestion import metadata
    from book_ingestion.extractors import base
    assert metadata is not None
    assert base is not None
