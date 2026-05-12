"""Tests for the disk cache."""
from __future__ import annotations

from pathlib import Path

from book_ingestion.cache import (
    Cache,
    sha256_of_file,
)


def _write_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def test_sha256_of_file(tmp_path: Path) -> None:
    p = tmp_path / "f.bin"
    _write_bytes(p, b"hello world")
    digest = sha256_of_file(p)
    assert len(digest) == 64
    assert digest == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_cache_roundtrip_payload(tmp_cache_dir: Path, tmp_path: Path) -> None:
    book = tmp_path / "book.pdf"
    _write_bytes(book, b"%PDF-1.4 ... contents ...")
    cache = Cache(root=tmp_cache_dir)

    payload = {"hello": "world", "answer": 42}
    cache.write(book, "survey.json", payload)

    loaded = cache.read(book, "survey.json")
    assert loaded == payload


def test_cache_miss_returns_none(tmp_cache_dir: Path, tmp_path: Path) -> None:
    book = tmp_path / "book.pdf"
    _write_bytes(book, b"hi")
    cache = Cache(root=tmp_cache_dir)

    assert cache.read(book, "survey.json") is None


def test_schema_version_invalidates_entry(tmp_cache_dir: Path, tmp_path: Path) -> None:
    book = tmp_path / "book.pdf"
    _write_bytes(book, b"x")
    cache = Cache(root=tmp_cache_dir, schema_version="1.0")
    cache.write(book, "survey.json", {"a": 1})

    cache_v2 = Cache(root=tmp_cache_dir, schema_version="2.0")
    assert cache_v2.read(book, "survey.json") is None


def test_cache_dir_path(tmp_cache_dir: Path, tmp_path: Path) -> None:
    book = tmp_path / "book.pdf"
    _write_bytes(book, b"y")
    cache = Cache(root=tmp_cache_dir)
    dir_for = cache.dir_for(book)
    digest = sha256_of_file(book)
    assert dir_for == tmp_cache_dir / digest
