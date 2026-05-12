"""Smoke gate — under 5s. Asserts the package imports."""
from __future__ import annotations


def test_package_imports() -> None:
    import book_ingestion

    assert book_ingestion.__version__ == "0.1.0"
