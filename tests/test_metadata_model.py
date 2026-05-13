"""Tests for the BookMetadata Pydantic model and its sub-models."""
from __future__ import annotations


def test_imports() -> None:
    from book_ingestion import metadata  # noqa: F401
    from book_ingestion.extractors import base  # noqa: F401
