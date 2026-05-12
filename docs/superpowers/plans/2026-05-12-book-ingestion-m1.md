# book-ingestion M1 (PDF MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the v1 (M1) PDF MVP of `book_ingestion` — a Python library + CLI that, given a digital PDF, produces a `BookSurvey` JSON (chapter map + quality) and a `ChapterContent` JSON per chapter (page-anchored blocks + quality), driven end-to-end by Docling.

**Architecture:** Docling is the PDF parsing engine. Our value-add is (a) a chapter map overlay with provenance tagging, (b) a projection from Docling's hierarchical tree into a flat `simple_view` block list per chapter, (c) a content-hash-keyed disk cache, (d) a typed quality model, and (e) a Typer CLI plus a clean Python API. See `docs/superpowers/specs/2026-05-12-book-ingestion-design.md` for the full design.

**Tech Stack:** Python 3.11+, Docling ≥2.93, Pydantic v2 ≥2.13, Typer ≥0.25, pytest ≥9, syrupy ≥5.1, ruff ≥0.15, mypy ≥2.1, reportlab ≥4.5, uv + hatchling.

## Deviations from the design spec

These are intentional, scoped deviations from `docs/superpowers/specs/2026-05-12-book-ingestion-design.md`. Each is reversible; M2/M3 plans will revisit.

1. **No `syrupy` snapshot tests in M1.** The spec's §8 prescribes snapshot tests for the chapter map and per-chapter first-paragraph against bundled fixtures. M1 uses **structural integration tests** instead (assert that fields are populated and shapes are correct, not exact text). Rationale: there is no bundled arXiv fixture yet (the only real fixture is the test book, which is gitignored as copyright-restricted), and snapshot baselines built against the real book would be fragile across Docling versions. `syrupy` stays in `[dev]` deps so M2 can adopt it once the EPUB fixtures (Standard Ebooks, Project Gutenberg) are bundled and stable.
2. **`--llm-assist` is accepted but inert in M1.** The CLI exposes the flag and the API passes it through to `survey()`, but `structure/llm_assist.py` is an M4 file and is not created in this milestone. Passing `--llm-assist` in M1 has no observable effect; the spec's promised opt-in chapter-structure inference arrives in M4.

---

## File map

**Created in this milestone (all paths relative to repo root):**

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Project metadata, deps, tool config (ruff, mypy, pytest), uv lockfile target |
| `README.md` | Quickstart, install, CLI usage |
| `src/book_ingestion/__init__.py` | Public re-exports: `survey`, `extract_chapter`, IR models |
| `src/book_ingestion/ir.py` | Pydantic v2 models: `BookSurvey`, `ChapterContent`, block union, `Locator`, `Quality`, `Provenance`/`Confidence` enums, `SCHEMA_VERSION` |
| `src/book_ingestion/cache.py` | Content-hash-keyed disk cache; schema-version invalidation |
| `src/book_ingestion/detect.py` | Format sniffer (extension + magic bytes) |
| `src/book_ingestion/api.py` | `survey()` / `extract_chapter()` public functions; backend dispatch |
| `src/book_ingestion/cli.py` | Typer app: `survey`, `extract`, `cache list/clear` subcommands |
| `src/book_ingestion/backends/__init__.py` | Backend registry |
| `src/book_ingestion/backends/base.py` | `Backend` Protocol + `Context` dataclass |
| `src/book_ingestion/backends/pdf_docling.py` | The v1 PDF backend |
| `src/book_ingestion/structure/__init__.py` | (empty package init) |
| `src/book_ingestion/structure/embedded_toc.py` | Build chapter map from Docling's section hierarchy |
| `src/book_ingestion/projection/__init__.py` | (empty package init) |
| `src/book_ingestion/projection/to_simple_view.py` | DoclingDocument subtree → list of `simple_view` blocks |
| `src/book_ingestion/quality/__init__.py` | (empty package init) |
| `src/book_ingestion/quality/scoring.py` | Docling per-page scores → `Confidence` grade |
| `src/book_ingestion/quality/flags.py` | `KNOWN_FLAGS` set; emission rules |
| `tests/conftest.py` | Pytest fixtures: tmp cache dir, synthetic PDF factory, minimal DoclingDocument factory |
| `tests/test_ir.py` | IR round-trip, discriminated union, schema-version constant |
| `tests/test_cache.py` | Hash keying, schema-version invalidation, `--no-cache` write-through |
| `tests/test_detect.py` | Format sniffing |
| `tests/test_quality.py` | Score → grade mapping; `KNOWN_FLAGS` enforcement |
| `tests/test_structure.py` | Embedded TOC → chapter map |
| `tests/test_projection.py` | DoclingDocument → simple_view (paragraphs, headings, page-break split, footnote linking, table fallback, unknown-item → failed_region) |
| `tests/test_api.py` | `survey()` / `extract_chapter()` happy path on synthetic PDF |
| `tests/test_cli.py` | CLI exit codes, JSON-to-stdout |
| `tests/test_pdf_real.py` | Acceptance test against `test/What is Modern Israel…pdf` (slow) |
| `tests/snapshots/` | syrupy snapshots (auto-generated) |

**Not created in M1** (declared in `pyproject.toml` for future milestones but file-stubbed only if needed):
- `src/book_ingestion/backends/epub.py` (M2)
- `src/book_ingestion/backends/pdf_ocr.py` (M3)
- `src/book_ingestion/structure/typographic.py` (M3/M4)
- `src/book_ingestion/structure/llm_assist.py` (M4)

---

## Task 1: Scaffold project (pyproject + src layout + smoke gate)

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/book_ingestion/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "book-ingestion"
version = "0.1.0"
description = "Turn a book file into a JSON IR a downstream LLM workflow can consume"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "Richard Lyon" }]
dependencies = [
    "docling>=2.93",
    "pydantic>=2.13",
    "typer>=0.25",
]

[project.optional-dependencies]
llm = ["anthropic>=0.101"]
dev = [
    "pytest>=9.0",
    "syrupy>=5.1",
    "ruff>=0.15",
    "mypy>=2.1",
    "reportlab>=4.5",
]

[project.scripts]
book-ingest = "book_ingestion.cli:app"

[build-system]
requires = ["hatchling>=1.29"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/book_ingestion"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]
ignore = ["E501"]  # line-length handled by formatter

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src/book_ingestion"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "slow: integration tests that run real Docling (deselect with -m 'not slow')",
    "real_book: requires the real book in test/",
]
addopts = "-ra"
```

- [ ] **Step 2: Write `README.md`**

```markdown
# book-ingestion

Convert a local book file (PDF in v1; EPUB v2; scanned-PDF OCR v3) into a JSON intermediate representation an LLM workflow can consume.

See `architecture.md` for intent and `docs/superpowers/specs/2026-05-12-book-ingestion-design.md` for the design.

## Install

```bash
uv sync --extra dev
```

## Run

```bash
uv run book-ingest survey path/to/book.pdf
uv run book-ingest extract path/to/book.pdf --chapter 3
```

## Develop

```bash
uv run pytest                  # fast tests only
uv run pytest -m slow          # integration tests (real Docling)
uv run ruff check src tests
uv run mypy
```
```

- [ ] **Step 3: Write `src/book_ingestion/__init__.py` (empty for now; will re-export after API exists)**

```python
"""book_ingestion — turn a book into a JSON IR."""

__version__ = "0.1.0"
```

- [ ] **Step 4: Write `tests/__init__.py`**

```python
```

(Empty file.)

- [ ] **Step 5: Write `tests/conftest.py` with a synthetic-PDF factory using ReportLab**

```python
"""Shared test fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """A clean cache directory scoped to the test."""
    d = tmp_path / "cache"
    d.mkdir()
    return d


@pytest.fixture
def synthetic_pdf(tmp_path: Path) -> Path:
    """A 1-page PDF with 3 paragraphs; deterministic content."""
    path = tmp_path / "synthetic.pdf"
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, 720, "Chapter 1 - The Beginning")
    c.setFont("Helvetica", 10)
    c.drawString(72, 690, "This is the first paragraph of the chapter.")
    c.drawString(72, 670, "Here is a second paragraph with more content.")
    c.drawString(72, 650, "And a third to round out the page.")
    c.showPage()
    c.save()
    return path
```

- [ ] **Step 6: Write the smoke test**

```python
"""Smoke gate — under 5s. Asserts the package imports."""
from __future__ import annotations


def test_package_imports() -> None:
    import book_ingestion

    assert book_ingestion.__version__ == "0.1.0"
```

Save as `tests/test_smoke.py`.

- [ ] **Step 7: Initialize the venv and verify install**

Run:
```bash
uv sync --extra dev
```
Expected: lockfile written; all dev deps installed.

- [ ] **Step 8: Run the smoke test**

Run:
```bash
uv run pytest tests/test_smoke.py -v
```
Expected: 1 passed.

- [ ] **Step 9: Run ruff and mypy as sanity gates**

Run:
```bash
uv run ruff check src tests
uv run mypy
```
Expected: both clean.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml README.md src tests uv.lock
git commit -m "chore: scaffold project (pyproject, src layout, smoke gate)"
```

---

## Task 2: IR data models (Pydantic v2)

**Files:**
- Create: `src/book_ingestion/ir.py`
- Create: `tests/test_ir.py`

- [ ] **Step 1: Write the failing test for IR shapes and round-trip**

```python
"""Tests for the IR models."""
from __future__ import annotations

import json

from book_ingestion.ir import (
    SCHEMA_VERSION,
    BookSurvey,
    Chapter,
    ChapterContent,
    Confidence,
    Heading,
    MapInfo,
    Paragraph,
    PageRange,
    Provenance,
    Quality,
    Source,
)


def test_schema_version_is_one_zero() -> None:
    assert SCHEMA_VERSION == "1.0"


def test_book_survey_round_trip() -> None:
    survey = BookSurvey(
        schema_version=SCHEMA_VERSION,
        source=Source(path="/tmp/book.pdf", sha256="ab" * 32, size_bytes=4096, format="pdf"),
        metadata={"title": "A Book", "authors": ["Someone"]},
        chapters=[
            Chapter(
                index=0,
                title="Introduction",
                locator=PageRange(start_page=1, end_page=10),
                provenance=Provenance.EMBEDDED,
                confidence=Confidence.EXCELLENT,
            )
        ],
        map=MapInfo(provenance=Provenance.EMBEDDED, confidence=Confidence.GOOD, method="pdf_outline"),
        quality=Quality(backend="docling_pdf", flags=[]),
        cache_paths={"docling_document": "/tmp/docling.json"},
    )
    dumped = survey.model_dump(mode="json")
    again = BookSurvey.model_validate(dumped)
    assert again == survey
    # JSON serialization works
    json.dumps(dumped)


def test_chapter_content_with_failed_region() -> None:
    content = ChapterContent(
        schema_version=SCHEMA_VERSION,
        source=Source(path="/tmp/book.pdf", sha256="ab" * 32, size_bytes=4096, format="pdf"),
        chapter=Chapter(
            index=3,
            title="Chapter 3",
            locator=PageRange(start_page=142, end_page=178),
            provenance=Provenance.EMBEDDED,
            confidence=Confidence.GOOD,
        ),
        simple_view=[
            Heading(text="Chapter 3", level=1, page=142, confidence=Confidence.EXCELLENT),
            Paragraph(text="Hello.", page=142, confidence=Confidence.EXCELLENT),
        ],
        quality=Quality(backend="docling_pdf", flags=[]),
        cache_paths={"docling_chapter": "/tmp/chapter-3.docling.json"},
    )
    dumped = content.model_dump(mode="json")
    again = ChapterContent.model_validate(dumped)
    assert again == content


def test_locator_discriminated_union() -> None:
    """PageRange and SpineRange both deserialize via kind discriminator."""
    page = PageRange.model_validate({"kind": "page_range", "start_page": 1, "end_page": 10})
    assert page.start_page == 1
    # A future SpineRange would also deserialize; for now just check the kind field.
    assert page.kind == "page_range"
```

Save as `tests/test_ir.py`.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_ir.py -v
```
Expected: ImportError (module `book_ingestion.ir` not defined).

- [ ] **Step 3: Implement `src/book_ingestion/ir.py`**

```python
"""Intermediate representation models for book ingestion.

All payloads serialize to JSON via `.model_dump(mode='json')`. Every payload
carries a `schema_version` at the root; consumers must check it before parsing.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


class Provenance(str, Enum):
    EMBEDDED = "embedded"
    INFERRED = "inferred"
    LLM_ASSISTED = "llm_assisted"
    NONE = "none"


class Confidence(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


# ---- Locators -----------------------------------------------------------

class PageRange(BaseModel):
    """PDF locator: an inclusive page range."""
    model_config = ConfigDict(frozen=True)
    kind: Literal["page_range"] = "page_range"
    start_page: int
    end_page: int


class SpineRange(BaseModel):
    """EPUB locator (v2): a range across spine items."""
    model_config = ConfigDict(frozen=True)
    kind: Literal["spine_range"] = "spine_range"
    start_spine: int
    end_spine: int
    start_frag: str | None = None
    end_frag: str | None = None


Locator = Annotated[Union[PageRange, SpineRange], Field(discriminator="kind")]


# ---- Source and survey --------------------------------------------------

class Source(BaseModel):
    model_config = ConfigDict(frozen=True)
    path: str
    sha256: str
    size_bytes: int
    format: Literal["pdf", "epub"]


class Chapter(BaseModel):
    model_config = ConfigDict(frozen=True)
    index: int
    title: str
    locator: Locator
    provenance: Provenance
    confidence: Confidence


class MapInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    provenance: Provenance
    confidence: Confidence
    method: str  # short tag: "pdf_outline" | "typographic" | "llm_assist" | "none"


class Quality(BaseModel):
    backend: str
    docling_mean_grade: Confidence | None = None
    docling_low_grade: Confidence | None = None
    pages_total: int | None = None
    pages_with_extraction_failures: int = 0
    pages_processed: list[int] = Field(default_factory=list)
    pages_with_failures: list[int] = Field(default_factory=list)
    block_confidence_counts: dict[str, int] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)


# ---- Blocks (simple_view) -----------------------------------------------

class Paragraph(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["paragraph"] = "paragraph"
    text: str
    page: int | None = None
    confidence: Confidence
    footnote_refs: list[str] = Field(default_factory=list)
    list_marker: str | None = None
    continued_from: str | None = None


class Heading(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["heading"] = "heading"
    text: str
    level: int = Field(ge=1, le=6)
    page: int | None = None
    confidence: Confidence


class Table(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["table"] = "table"
    page: int | None = None
    confidence: Confidence
    rows: list[list[str]] | None = None
    raw_text: str


class FigureCaption(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["figure_caption"] = "figure_caption"
    text: str
    page: int | None = None
    confidence: Confidence


class Footnote(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["footnote"] = "footnote"
    id: str
    text: str
    page: int | None = None
    confidence: Confidence


class PageBreak(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["page_break"] = "page_break"
    page: int


class FailedRegion(BaseModel):
    model_config = ConfigDict(frozen=True)
    type: Literal["failed_region"] = "failed_region"
    page: int | None = None
    reason: str
    raw_text: str | None = None


Block = Annotated[
    Union[Paragraph, Heading, Table, FigureCaption, Footnote, PageBreak, FailedRegion],
    Field(discriminator="type"),
]


# ---- Top-level payloads -------------------------------------------------

class BookSurvey(BaseModel):
    schema_version: str
    kind: Literal["book_survey"] = "book_survey"
    source: Source
    metadata: dict[str, Any] = Field(default_factory=dict)
    chapters: list[Chapter] = Field(default_factory=list)
    map: MapInfo
    quality: Quality
    cache_paths: dict[str, str] = Field(default_factory=dict)


class ChapterContent(BaseModel):
    schema_version: str
    kind: Literal["chapter_content"] = "chapter_content"
    source: Source
    chapter: Chapter
    simple_view: list[Block] = Field(default_factory=list)
    quality: Quality
    docling_document: None = None  # always null inline; see cache_paths
    cache_paths: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_ir.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Run ruff + mypy**

Run:
```bash
uv run ruff check src tests && uv run mypy
```
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/ir.py tests/test_ir.py
git commit -m "feat(ir): add Pydantic v2 models for BookSurvey, ChapterContent, blocks"
```

---

## Task 3: Cache (content-hash keyed, schema-version invalidated)

**Files:**
- Create: `src/book_ingestion/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the disk cache."""
from __future__ import annotations

import json
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
    # 64 hex chars
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

    # Same digest, different schema version → miss.
    cache_v2 = Cache(root=tmp_cache_dir, schema_version="2.0")
    assert cache_v2.read(book, "survey.json") is None


def test_cache_dir_path(tmp_cache_dir: Path, tmp_path: Path) -> None:
    book = tmp_path / "book.pdf"
    _write_bytes(book, b"y")
    cache = Cache(root=tmp_cache_dir)
    dir_for = cache.dir_for(book)
    digest = sha256_of_file(book)
    assert dir_for == tmp_cache_dir / digest
```

Save as `tests/test_cache.py`.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_cache.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `src/book_ingestion/cache.py`**

```python
"""Content-hash-keyed disk cache.

The cache key is the sha256 of the file *content*, not its path. Each cached
entry is stored under `~/.cache/book-ingestion/<sha256>/`. A `meta.json` records
the `schema_version`; mismatches invalidate the entry transparently.

The cache is opaque to callers: `cache_paths.*` fields in the IR are convenience
pointers, but consumers must never write into the cache themselves.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from book_ingestion.ir import SCHEMA_VERSION

logger = logging.getLogger(__name__)

_CHUNK = 1 << 20  # 1 MiB


def sha256_of_file(path: Path) -> str:
    """Streaming sha256 of file content."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def default_cache_root() -> Path:
    return Path.home() / ".cache" / "book-ingestion"


class Cache:
    """Disk cache scoped to a content-hash directory."""

    def __init__(self, root: Path | None = None, schema_version: str = SCHEMA_VERSION) -> None:
        self.root = root if root is not None else default_cache_root()
        self.schema_version = schema_version
        self.root.mkdir(parents=True, exist_ok=True)

    def dir_for(self, path: Path) -> Path:
        digest = sha256_of_file(path)
        return self.root / digest

    def _meta_path(self, path: Path) -> Path:
        return self.dir_for(path) / "meta.json"

    def _ensure_meta(self, path: Path) -> None:
        """Write meta.json if absent. If present with mismatched schema, leave it
        as-is (read() will detect the mismatch and invalidate)."""
        d = self.dir_for(path)
        d.mkdir(parents=True, exist_ok=True)
        meta_path = self._meta_path(path)
        if not meta_path.exists():
            meta = {
                "origin_path": str(path),
                "size_bytes": path.stat().st_size,
                "schema_version": self.schema_version,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            meta_path.write_text(json.dumps(meta, indent=2))

    def _entry_valid(self, path: Path) -> bool:
        meta_path = self._meta_path(path)
        if not meta_path.exists():
            return False
        try:
            meta = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            return False
        return bool(meta.get("schema_version") == self.schema_version)

    def write(self, path: Path, name: str, payload: Any) -> Path:
        """Write a JSON payload to <cache>/<sha256>/<name>. Creates meta.json if missing."""
        self._ensure_meta(path)
        target = self.dir_for(path) / name
        target.write_text(json.dumps(payload, indent=2))
        return target

    def read(self, path: Path, name: str) -> Any | None:
        """Return the cached JSON payload or None on miss / invalidation."""
        if not self._entry_valid(path):
            if self._meta_path(path).exists():
                logger.info(
                    "cache entry schema-version mismatch; invalidating %s",
                    self.dir_for(path),
                )
            return None
        target = self.dir_for(path) / name
        if not target.exists():
            return None
        try:
            return json.loads(target.read_text())
        except json.JSONDecodeError:
            return None

    def clear(self, path: Path) -> None:
        """Remove the cache directory for a single file. No-op if absent."""
        d = self.dir_for(path)
        if d.exists():
            for p in d.iterdir():
                p.unlink()
            d.rmdir()
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_cache.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Run ruff + mypy**

Run:
```bash
uv run ruff check src tests && uv run mypy
```
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/cache.py tests/test_cache.py
git commit -m "feat(cache): add content-hash-keyed disk cache with schema-version invalidation"
```

---

## Task 4: Detect (format sniffer)

**Files:**
- Create: `src/book_ingestion/detect.py`
- Create: `tests/test_detect.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the format sniffer."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion.detect import detect_format


def test_detect_pdf_by_magic_and_extension(tmp_path: Path) -> None:
    p = tmp_path / "book.pdf"
    p.write_bytes(b"%PDF-1.7\nrest")
    assert detect_format(p) == "pdf"


def test_detect_epub_by_extension_and_zip_magic(tmp_path: Path) -> None:
    p = tmp_path / "book.epub"
    # EPUBs are zip files; "PK\x03\x04" is the local-file-header magic.
    p.write_bytes(b"PK\x03\x04rest_of_zip")
    assert detect_format(p) == "epub"


def test_detect_rejects_unsupported(tmp_path: Path) -> None:
    p = tmp_path / "book.txt"
    p.write_bytes(b"plain text")
    with pytest.raises(ValueError, match="unsupported format"):
        detect_format(p)


def test_detect_rejects_extension_mismatch(tmp_path: Path) -> None:
    p = tmp_path / "book.pdf"
    p.write_bytes(b"not a pdf")
    with pytest.raises(ValueError, match="not a valid PDF"):
        detect_format(p)
```

Save as `tests/test_detect.py`.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_detect.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `src/book_ingestion/detect.py`**

```python
"""Sniff the format of an input file.

Routes to a backend by extension first, then verifies the file's magic bytes
match before returning. This catches accidental mis-extensions early.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

Format = Literal["pdf", "epub"]

_PDF_MAGIC = b"%PDF"
_ZIP_MAGIC = b"PK\x03\x04"  # EPUB is a zip
_SNIFF_BYTES = 8


def detect_format(path: Path) -> Format:
    """Return the format tag of `path`.

    Raises ValueError when the file does not match a supported format or when
    the extension and the magic bytes disagree.
    """
    suffix = path.suffix.lower()
    with path.open("rb") as f:
        head = f.read(_SNIFF_BYTES)

    if suffix == ".pdf":
        if not head.startswith(_PDF_MAGIC):
            raise ValueError(f"{path} has .pdf extension but is not a valid PDF (magic mismatch)")
        return "pdf"
    if suffix == ".epub":
        if not head.startswith(_ZIP_MAGIC):
            raise ValueError(f"{path} has .epub extension but is not a valid EPUB (zip magic mismatch)")
        return "epub"

    raise ValueError(f"unsupported format: {path.name} (suffix: {suffix or 'none'})")
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_detect.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Run ruff + mypy and commit**

```bash
uv run ruff check src tests && uv run mypy
git add src/book_ingestion/detect.py tests/test_detect.py
git commit -m "feat(detect): add format sniffer (extension + magic-bytes)"
```

---

## Task 5: Backend Protocol + registry skeleton

**Files:**
- Create: `src/book_ingestion/backends/__init__.py`
- Create: `src/book_ingestion/backends/base.py`

This task has no test of its own — it's a contract module. Tests in later tasks exercise it.

- [ ] **Step 1: Write `src/book_ingestion/backends/base.py`**

```python
"""Backend Protocol and shared Context.

Each backend (pdf, epub, pdf_ocr) implements `Backend`. `api.py` dispatches to
the right one based on `detect.detect_format()`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from book_ingestion.cache import Cache
from book_ingestion.ir import BookSurvey, ChapterContent


@dataclass(frozen=True)
class Context:
    """Per-call execution context passed to backends."""
    cache: Cache
    use_cache: bool = True
    llm_assist: bool = False


class Backend(Protocol):
    """The interface every backend implements."""

    name: str

    def survey(self, path: Path, *, ctx: Context) -> BookSurvey: ...

    def extract_chapter(self, path: Path, chapter_index: int, *, ctx: Context) -> ChapterContent: ...
```

- [ ] **Step 2: Write `src/book_ingestion/backends/__init__.py`**

```python
"""Backend registry. v1 exposes the pdf backend only."""
from __future__ import annotations

from book_ingestion.backends.base import Backend, Context

# Populated lazily by api.py to avoid eager imports of heavy deps (Docling).
__all__ = ["Backend", "Context"]
```

- [ ] **Step 3: Verify imports**

Run:
```bash
uv run python -c "from book_ingestion.backends.base import Backend, Context; print('ok')"
```
Expected: `ok`.

- [ ] **Step 4: Run ruff + mypy and commit**

```bash
uv run ruff check src tests && uv run mypy
git add src/book_ingestion/backends/
git commit -m "feat(backends): add Backend Protocol and Context"
```

---

## Task 6: Quality model (scoring + flags)

**Files:**
- Create: `src/book_ingestion/quality/__init__.py`
- Create: `src/book_ingestion/quality/scoring.py`
- Create: `src/book_ingestion/quality/flags.py`
- Create: `tests/test_quality.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for quality scoring and flags."""
from __future__ import annotations

import pytest

from book_ingestion.ir import Confidence
from book_ingestion.quality.flags import KNOWN_FLAGS, validate_flag
from book_ingestion.quality.scoring import grade_from_score


@pytest.mark.parametrize(
    ("score", "grade"),
    [
        (0.95, Confidence.EXCELLENT),
        (0.80, Confidence.GOOD),
        (0.60, Confidence.FAIR),
        (0.30, Confidence.POOR),
        (0.0, Confidence.POOR),
    ],
)
def test_grade_from_score(score: float, grade: Confidence) -> None:
    assert grade_from_score(score) == grade


def test_known_flags_contains_expected() -> None:
    expected = {
        "ocr_used",
        "ocr_low_confidence_block",
        "ocr_severely_degraded",
        "two_column_layout",
        "mixed_layout",
        "embedded_toc_present",
        "toc_inferred",
        "toc_unresolved",
        "tables_present",
        "table_structure_uncertain",
        "unicode_normalization_failure",
        "llm_assist_used",
        "unparseable",
    }
    assert expected <= KNOWN_FLAGS


def test_validate_flag_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown quality flag"):
        validate_flag("totally_made_up_flag")


def test_validate_flag_accepts_known() -> None:
    # No exception
    validate_flag("ocr_used")
```

Save as `tests/test_quality.py`.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_quality.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `src/book_ingestion/quality/__init__.py`**

```python
"""Quality scoring and flag emission."""
```

- [ ] **Step 4: Implement `src/book_ingestion/quality/scoring.py`**

```python
"""Map numeric Docling scores into our categorical Confidence grade.

Thresholds match Docling's own grade boundaries closely. See:
https://docling-project.github.io/docling/concepts/confidence_scores/
"""
from __future__ import annotations

from book_ingestion.ir import Confidence

_EXCELLENT = 0.90
_GOOD = 0.75
_FAIR = 0.50


def grade_from_score(score: float) -> Confidence:
    """Convert a Docling score in [0, 1] to a Confidence grade."""
    if score >= _EXCELLENT:
        return Confidence.EXCELLENT
    if score >= _GOOD:
        return Confidence.GOOD
    if score >= _FAIR:
        return Confidence.FAIR
    return Confidence.POOR
```

- [ ] **Step 5: Implement `src/book_ingestion/quality/flags.py`**

```python
"""Vocabulary of quality flags.

Every value emitted into `BookSurvey.quality.flags` or `ChapterContent.quality.flags`
must be in `KNOWN_FLAGS`. This keeps the vocabulary documented in one place and
prevents drift in what downstream consumers must understand.
"""
from __future__ import annotations

KNOWN_FLAGS: frozenset[str] = frozenset(
    {
        # OCR
        "ocr_used",
        "ocr_low_confidence_block",
        "ocr_severely_degraded",
        # Layout
        "two_column_layout",
        "mixed_layout",
        # Structure / TOC
        "embedded_toc_present",
        "toc_inferred",
        "toc_unresolved",
        # Tables
        "tables_present",
        "table_structure_uncertain",
        # Text quality
        "unicode_normalization_failure",
        # Tool state
        "llm_assist_used",
        # Whole-document refusal
        "unparseable",
    }
)


def validate_flag(flag: str) -> None:
    """Raise ValueError if `flag` is not in `KNOWN_FLAGS`.

    Use this at every emission site to keep the vocabulary stable.
    """
    if flag not in KNOWN_FLAGS:
        raise ValueError(
            f"unknown quality flag: {flag!r}. Add it to KNOWN_FLAGS with a comment."
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_quality.py -v
```
Expected: 8 passed.

- [ ] **Step 7: Run ruff + mypy and commit**

```bash
uv run ruff check src tests && uv run mypy
git add src/book_ingestion/quality/ tests/test_quality.py
git commit -m "feat(quality): add scoring grade-map and KNOWN_FLAGS vocabulary"
```

---

## Task 7: Structure — embedded TOC → chapter map

**Files:**
- Create: `src/book_ingestion/structure/__init__.py`
- Create: `src/book_ingestion/structure/embedded_toc.py`
- Create: `tests/test_structure.py`

This task uses a hand-rolled in-memory representation of "what Docling gives us" (`_HeadingHint`) so unit tests don't need to spin up Docling. The PDF backend in Task 9 adapts the real `DoclingDocument` into this shape before calling.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the chapter-map builder."""
from __future__ import annotations

from book_ingestion.ir import Confidence, MapInfo, PageRange, Provenance
from book_ingestion.structure.embedded_toc import HeadingHint, build_chapter_map


def test_no_headings_returns_empty_map() -> None:
    chapters, info = build_chapter_map([], total_pages=100)
    assert chapters == []
    assert info.provenance == Provenance.NONE
    assert info.confidence == Confidence.POOR
    assert info.method == "none"


def test_top_level_headings_become_chapters() -> None:
    hints = [
        HeadingHint(text="Chapter 1 — Introduction", level=1, page=1),
        HeadingHint(text="Chapter 2 — Methods", level=1, page=20),
        HeadingHint(text="Chapter 3 — Results", level=1, page=50),
    ]
    chapters, info = build_chapter_map(hints, total_pages=100)
    assert [c.title for c in chapters] == [
        "Chapter 1 — Introduction",
        "Chapter 2 — Methods",
        "Chapter 3 — Results",
    ]
    assert isinstance(chapters[0].locator, PageRange)
    assert chapters[0].locator.start_page == 1
    assert chapters[0].locator.end_page == 19   # one before the next chapter
    assert chapters[1].locator.end_page == 49
    assert chapters[2].locator.end_page == 100  # last chapter runs to end
    assert info.provenance == Provenance.EMBEDDED
    assert info.method == "pdf_outline"


def test_sub_headings_are_ignored_at_chapter_level() -> None:
    hints = [
        HeadingHint(text="Chapter 1", level=1, page=1),
        HeadingHint(text="1.1 Sub", level=2, page=5),
        HeadingHint(text="Chapter 2", level=1, page=10),
    ]
    chapters, _ = build_chapter_map(hints, total_pages=20)
    assert len(chapters) == 2
    assert chapters[0].locator.end_page == 9


def test_single_chapter_runs_to_last_page() -> None:
    hints = [HeadingHint(text="Sole Chapter", level=1, page=1)]
    chapters, _ = build_chapter_map(hints, total_pages=10)
    assert chapters[0].locator.end_page == 10


def test_chapter_indices_are_zero_based_and_dense() -> None:
    hints = [
        HeadingHint(text="A", level=1, page=1),
        HeadingHint(text="B", level=1, page=5),
        HeadingHint(text="C", level=1, page=9),
    ]
    chapters, _ = build_chapter_map(hints, total_pages=12)
    assert [c.index for c in chapters] == [0, 1, 2]


def test_returns_inferred_when_caller_says_so() -> None:
    hints = [HeadingHint(text="A", level=1, page=1)]
    _, info = build_chapter_map(hints, total_pages=10, provenance=Provenance.INFERRED, method="typographic")
    assert info.provenance == Provenance.INFERRED
    assert info.method == "typographic"
```

Save as `tests/test_structure.py`.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_structure.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `src/book_ingestion/structure/__init__.py`**

```python
"""Chapter structure extraction."""
```

- [ ] **Step 4: Implement `src/book_ingestion/structure/embedded_toc.py`**

```python
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
    level: int    # 1 = top-level (treated as chapter); 2+ = subsection
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
        end = (top_level[i + 1].page - 1) if i + 1 < len(top_level) else total_pages
        chapters.append(
            Chapter(
                index=i,
                title=h.text,
                locator=PageRange(start_page=h.page, end_page=end),
                provenance=provenance,
                confidence=Confidence.EXCELLENT if provenance == Provenance.EMBEDDED else Confidence.FAIR,
            )
        )

    # Map confidence: embedded → GOOD; inferred → FAIR; llm_assisted → FAIR.
    map_conf = Confidence.GOOD if provenance == Provenance.EMBEDDED else Confidence.FAIR
    return chapters, MapInfo(provenance=provenance, confidence=map_conf, method=method)
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_structure.py -v
```
Expected: 6 passed.

- [ ] **Step 6: Run ruff + mypy and commit**

```bash
uv run ruff check src tests && uv run mypy
git add src/book_ingestion/structure/ tests/test_structure.py
git commit -m "feat(structure): build chapter map from heading hints"
```

---

## Task 8: Projection — DoclingDocument → simple_view

This is the longest task. We test against a *small in-memory adapter type* that mirrors the subset of DoclingDocument's surface we use, so unit tests don't need a real PDF. The PDF backend in Task 10 will pass actual Docling items through.

**Files:**
- Create: `src/book_ingestion/projection/__init__.py`
- Create: `src/book_ingestion/projection/to_simple_view.py`
- Create: `tests/test_projection.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for DoclingDocument → simple_view projection."""
from __future__ import annotations

from book_ingestion.ir import (
    Confidence,
    FailedRegion,
    FigureCaption,
    Footnote,
    Heading,
    PageBreak,
    Paragraph,
    Table,
)
from book_ingestion.projection.to_simple_view import (
    DoclingItem,
    ItemKind,
    project_to_simple_view,
)


def _item(kind: ItemKind, *, text: str = "", page: int, score: float = 0.95, **extra: object) -> DoclingItem:
    return DoclingItem(kind=kind, text=text, page=page, score=score, extra=dict(extra))


def test_paragraphs_and_headings_basic() -> None:
    items = [
        _item("heading", text="Chapter 3", page=10, level=1),
        _item("paragraph", text="First.", page=10),
        _item("paragraph", text="Second.", page=10),
    ]
    blocks = project_to_simple_view(items)
    assert blocks == [
        Heading(text="Chapter 3", level=1, page=10, confidence=Confidence.EXCELLENT),
        Paragraph(text="First.", page=10, confidence=Confidence.EXCELLENT),
        Paragraph(text="Second.", page=10, confidence=Confidence.EXCELLENT),
    ]


def test_page_break_inserted_between_pages() -> None:
    items = [
        _item("paragraph", text="On 10.", page=10),
        _item("paragraph", text="On 11.", page=11),
    ]
    blocks = project_to_simple_view(items)
    assert blocks[0] == Paragraph(text="On 10.", page=10, confidence=Confidence.EXCELLENT)
    assert blocks[1] == PageBreak(page=11)
    assert blocks[2] == Paragraph(text="On 11.", page=11, confidence=Confidence.EXCELLENT)


def test_table_kept_structured_when_good() -> None:
    items = [_item("table", page=20, score=0.92, rows=[["a", "b"], ["c", "d"]], raw_text="a b\nc d")]
    blocks = project_to_simple_view(items)
    assert blocks == [
        Table(page=20, confidence=Confidence.EXCELLENT, rows=[["a", "b"], ["c", "d"]], raw_text="a b\nc d"),
    ]


def test_table_falls_back_to_raw_text_when_uncertain() -> None:
    items = [_item("table", page=20, score=0.55, rows=[["a", "b"]], raw_text="a b")]
    blocks = project_to_simple_view(items)
    assert blocks == [
        Table(page=20, confidence=Confidence.FAIR, rows=None, raw_text="a b"),
    ]


def test_figure_caption() -> None:
    items = [_item("figure_caption", text="Figure 1.", page=15)]
    assert project_to_simple_view(items) == [
        FigureCaption(text="Figure 1.", page=15, confidence=Confidence.EXCELLENT)
    ]


def test_footnote_emitted_with_id() -> None:
    items = [
        _item("paragraph", text="A claim.", page=10, footnote_ref="fn-1"),
        _item("footnote", text="See ...", page=10, fn_id="fn-1"),
    ]
    blocks = project_to_simple_view(items)
    assert blocks[0] == Paragraph(
        text="A claim.", page=10, confidence=Confidence.EXCELLENT, footnote_refs=["fn-1"]
    )
    assert blocks[1] == Footnote(id="fn-1", text="See ...", page=10, confidence=Confidence.EXCELLENT)


def test_unknown_kind_becomes_failed_region() -> None:
    items = [_item("totally_unknown", text="???", page=5)]  # type: ignore[arg-type]
    blocks = project_to_simple_view(items)
    assert blocks == [
        FailedRegion(page=5, reason="unknown_item_type", raw_text="???"),
    ]


def test_poor_score_paragraph_becomes_failed_region() -> None:
    items = [_item("paragraph", text="garbled", page=8, score=0.10)]
    blocks = project_to_simple_view(items)
    assert blocks == [
        FailedRegion(page=8, reason="low_confidence_extraction", raw_text="garbled"),
    ]
```

Save as `tests/test_projection.py`.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_projection.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `src/book_ingestion/projection/__init__.py`**

```python
"""Projection from DoclingDocument items to simple_view blocks."""
```

- [ ] **Step 4: Implement `src/book_ingestion/projection/to_simple_view.py`**

```python
"""Project a stream of Docling items into a simple_view block list.

The PDF backend (`backends/pdf_docling.py`) walks the real `DoclingDocument`
via `iterate_items()` and adapts each Docling item into the small `DoclingItem`
dataclass below. This separation keeps the projection logic unit-testable
without spinning up the full engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from book_ingestion.ir import (
    Block,
    Confidence,
    FailedRegion,
    FigureCaption,
    Footnote,
    Heading,
    PageBreak,
    Paragraph,
    Table,
)
from book_ingestion.quality.scoring import grade_from_score

ItemKind = Literal[
    "heading",
    "paragraph",
    "list_item",
    "table",
    "figure_caption",
    "footnote",
]


@dataclass(frozen=True)
class DoclingItem:
    """Adapter type bridging the real DoclingDocument items and our projection.

    `extra` carries kind-specific fields:
      - heading:        {"level": int}
      - paragraph:      {"footnote_ref": str | None, "list_marker": str | None}
      - table:          {"rows": list[list[str]] | None, "raw_text": str}
      - footnote:       {"fn_id": str}
    """
    kind: ItemKind
    text: str
    page: int
    score: float
    extra: dict[str, Any] = field(default_factory=dict)


_LOW_CONFIDENCE = Confidence.FAIR  # < FAIR → failed_region
_FAILED_REGION_THRESHOLD = {Confidence.POOR}


def project_to_simple_view(items: list[DoclingItem]) -> list[Block]:
    """Convert items to a list of simple_view blocks, inserting page_breaks
    between blocks that cross a page boundary."""
    blocks: list[Block] = []
    last_page: int | None = None

    for item in items:
        if last_page is not None and item.page != last_page:
            blocks.append(PageBreak(page=item.page))
        last_page = item.page
        blocks.append(_project_one(item))

    return blocks


def _project_one(item: DoclingItem) -> Block:
    grade = grade_from_score(item.score)

    # Whole-paragraph extraction failure → failed_region.
    if item.kind == "paragraph" and grade in _FAILED_REGION_THRESHOLD:
        return FailedRegion(page=item.page, reason="low_confidence_extraction", raw_text=item.text)

    if item.kind == "heading":
        level = int(item.extra.get("level", 1))
        return Heading(text=item.text, level=level, page=item.page, confidence=grade)

    if item.kind in ("paragraph", "list_item"):
        ref = item.extra.get("footnote_ref")
        return Paragraph(
            text=item.text,
            page=item.page,
            confidence=grade,
            footnote_refs=[ref] if ref else [],
            list_marker=item.extra.get("list_marker"),
        )

    if item.kind == "table":
        rows = item.extra.get("rows")
        raw_text = item.extra.get("raw_text", "")
        # Only keep structured rows when confidence is GOOD or better.
        if grade in (Confidence.GOOD, Confidence.EXCELLENT) and rows:
            return Table(page=item.page, confidence=grade, rows=rows, raw_text=raw_text)
        return Table(page=item.page, confidence=grade, rows=None, raw_text=raw_text)

    if item.kind == "figure_caption":
        return FigureCaption(text=item.text, page=item.page, confidence=grade)

    if item.kind == "footnote":
        fn_id = str(item.extra.get("fn_id", "fn-?"))
        return Footnote(id=fn_id, text=item.text, page=item.page, confidence=grade)

    # Unrecognized kind — refuse rather than guess.
    return FailedRegion(page=item.page, reason="unknown_item_type", raw_text=item.text)
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_projection.py -v
```
Expected: 8 passed.

- [ ] **Step 6: Run ruff + mypy and commit**

```bash
uv run ruff check src tests && uv run mypy
git add src/book_ingestion/projection/ tests/test_projection.py
git commit -m "feat(projection): DoclingDocument items → simple_view blocks"
```

---

## Task 9: PDF backend — `survey()`

This task introduces Docling. The unit-style boundary is the `_adapt_docling_to_hints` and `_adapt_docling_to_items` helpers — pure functions that take real Docling types and emit our adapter types (`HeadingHint`, `DoclingItem`). The full `survey()` is exercised by an integration test (Task 13) and a synthetic-PDF test below.

**Files:**
- Create: `src/book_ingestion/backends/pdf_docling.py`
- Create: `tests/test_pdf_backend_survey.py`

- [ ] **Step 1: Write the failing test (using the synthetic PDF fixture)**

```python
"""Tests for the PDF backend's survey() path."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion.backends.base import Context
from book_ingestion.backends.pdf_docling import PdfDoclingBackend
from book_ingestion.cache import Cache


@pytest.mark.slow
def test_survey_synthetic_pdf_runs_end_to_end(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    """survey() on the 1-page synthetic PDF returns a valid BookSurvey.

    The exact chapter count depends on whether Docling treats 'Chapter 1 - The
    Beginning' as a heading on a 1-page doc. We assert structure, not specifics:
    - source.sha256 is populated
    - map.provenance is one of the four allowed values
    - quality.backend == 'docling_pdf'
    - cache_paths.docling_document points at an existing file
    """
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

    # Make Docling unavailable; if we touch it on the second call, ImportError.
    calls = {"n": 0}

    def _boom(*_a: object, **_k: object) -> None:
        calls["n"] += 1
        raise RuntimeError("docling must not be called on cache hit")

    monkeypatch.setattr(backend, "_run_docling", _boom)
    backend.survey(synthetic_pdf, ctx=ctx)
    assert calls["n"] == 0
```

Save as `tests/test_pdf_backend_survey.py`.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_pdf_backend_survey.py -v -m slow
```
Expected: ImportError.

- [ ] **Step 3: Implement `src/book_ingestion/backends/pdf_docling.py`**

```python
"""The v1 PDF backend, driven end-to-end by Docling."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from book_ingestion.backends.base import Context
from book_ingestion.ir import (
    SCHEMA_VERSION,
    BookSurvey,
    Confidence,
    Quality,
    Source,
)
from book_ingestion.quality.flags import validate_flag
from book_ingestion.quality.scoring import grade_from_score
from book_ingestion.structure.embedded_toc import HeadingHint, build_chapter_map

logger = logging.getLogger(__name__)


class PdfDoclingBackend:
    """PDF backend. Survey + extract via Docling's DocumentConverter."""

    name = "docling_pdf"

    # --- public surface ---------------------------------------------------

    def survey(self, path: Path, *, ctx: Context) -> BookSurvey:
        # Cache hit on the previously-built survey?
        if ctx.use_cache:
            cached = ctx.cache.read(path, "survey.json")
            if cached is not None:
                return BookSurvey.model_validate(cached)

        # Otherwise run Docling once (cached separately as docling.json) and
        # rebuild the survey from it.
        docling_dict = self._get_or_run_docling(path, ctx=ctx)
        survey = self._build_survey(path, docling_dict, ctx=ctx)
        ctx.cache.write(path, "survey.json", survey.model_dump(mode="json"))
        return survey

    # --- internals --------------------------------------------------------

    def _get_or_run_docling(self, path: Path, *, ctx: Context) -> dict[str, Any]:
        if ctx.use_cache:
            cached = ctx.cache.read(path, "docling.json")
            if cached is not None:
                logger.info("docling cache hit for %s", path)
                return cached  # type: ignore[no-any-return]
        return self._run_docling(path, ctx=ctx)

    def _run_docling(self, path: Path, *, ctx: Context) -> dict[str, Any]:
        """Run Docling on the file and persist its serialized output.

        Returns a dict with three keys:
          - "document": the DoclingDocument as a dict (export_to_dict())
          - "confidence": flattened confidence report
          - "page_count": total pages
        """
        # Late import — keeps the lib startup-cheap when only IR types are needed.
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        logger.info("running docling on %s", path)
        result = converter.convert(str(path))

        doc_dict = result.document.export_to_dict()
        confidence = self._extract_confidence(result)
        page_count = self._page_count(result)

        payload = {
            "document": doc_dict,
            "confidence": confidence,
            "page_count": page_count,
        }
        ctx.cache.write(path, "docling.json", payload)
        return payload

    @staticmethod
    def _extract_confidence(result: Any) -> dict[str, Any]:
        """Flatten ConfidenceReport into a dict. Docling's exact attribute shape
        is library-version dependent; we tolerate missing fields."""
        conf = getattr(result, "confidence", None)
        if conf is None:
            return {"mean_grade": None, "low_grade": None, "scores": {}}
        return {
            "mean_grade": getattr(conf, "mean_grade", None),
            "low_grade": getattr(conf, "low_grade", None),
            "scores": {
                "parse": getattr(conf, "parse_score", None),
                "layout": getattr(conf, "layout_score", None),
                "ocr": getattr(conf, "ocr_score", None),
                "table": getattr(conf, "table_score", None),
            },
        }

    @staticmethod
    def _page_count(result: Any) -> int:
        pages = getattr(result, "pages", None) or []
        return len(pages) or 0

    def _build_survey(self, path: Path, docling: dict[str, Any], *, ctx: Context) -> BookSurvey:
        from book_ingestion.cache import sha256_of_file

        hints = self._extract_heading_hints(docling["document"])
        chapters, map_info = build_chapter_map(hints, total_pages=docling["page_count"] or 1)

        flags: list[str] = []
        if map_info.provenance.value == "embedded":
            flags.append("embedded_toc_present")
        elif map_info.provenance.value == "none":
            flags.append("toc_unresolved")
        for f in flags:
            validate_flag(f)

        conf = docling["confidence"]
        mean_grade = self._grade_field(conf.get("mean_grade"))
        low_grade = self._grade_field(conf.get("low_grade"))

        return BookSurvey(
            schema_version=SCHEMA_VERSION,
            source=Source(
                path=str(path.resolve()),
                sha256=sha256_of_file(path),
                size_bytes=path.stat().st_size,
                format="pdf",
            ),
            metadata=self._extract_metadata(docling["document"]),
            chapters=chapters,
            map=map_info,
            quality=Quality(
                backend=self.name,
                docling_mean_grade=mean_grade,
                docling_low_grade=low_grade,
                pages_total=docling["page_count"],
                flags=flags,
            ),
            cache_paths={"docling_document": str(ctx.cache.dir_for(path) / "docling.json")},
        )

    @staticmethod
    def _grade_field(raw: Any) -> Confidence | None:
        """Normalize a Docling grade (enum, string, or score) to our Confidence."""
        if raw is None:
            return None
        if isinstance(raw, str):
            # "EXCELLENT" / "GOOD" / "FAIR" / "POOR" pass straight through if valid.
            for c in Confidence:
                if raw == c.value:
                    return c
        if isinstance(raw, (int, float)):
            return grade_from_score(float(raw))
        # Enum-like: rely on .name or .value
        for attr in ("name", "value"):
            v = getattr(raw, attr, None)
            if isinstance(v, str):
                for c in Confidence:
                    if v == c.value:
                        return c
        return None

    @staticmethod
    def _extract_metadata(doc_dict: dict[str, Any]) -> dict[str, Any]:
        """Best-effort metadata lift from DoclingDocument JSON.

        DoclingDocument carries some metadata fields; we map them defensively.
        Unknown/missing fields become None.
        """
        md = (doc_dict.get("origin") or {}) if isinstance(doc_dict.get("origin"), dict) else {}
        return {
            "title": md.get("filename") or doc_dict.get("name") or None,
            "authors": [],
            "publisher": None,
            "year": None,
            "isbn": None,
            "language": None,
        }

    @staticmethod
    def _extract_heading_hints(doc_dict: dict[str, Any]) -> list[HeadingHint]:
        """Walk DoclingDocument JSON and emit HeadingHints.

        The exact shape of `texts[].label` and `texts[].prov` depends on
        DoclingDocument's serialization. We treat any item with a 'section_header'
        label (or DocItemLabel.SECTION_HEADER stringly) as a candidate; the
        item's prov[0].page_no gives the page.
        """
        hints: list[HeadingHint] = []
        texts = doc_dict.get("texts") or []
        for item in texts:
            label = str(item.get("label") or "").lower()
            if "section_header" not in label and "heading" not in label:
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            prov = item.get("prov") or []
            page = int(prov[0]["page_no"]) if prov and "page_no" in prov[0] else 1
            level = int(item.get("level") or 1)
            hints.append(HeadingHint(text=text, level=level, page=page))
        return hints
```

- [ ] **Step 4: Run test to verify it passes (note: slow; expect 10–60 s for Docling first-load)**

Run:
```bash
uv run pytest tests/test_pdf_backend_survey.py -v -m slow
```
Expected: 2 passed.

- [ ] **Step 5: Run ruff + mypy and commit**

```bash
uv run ruff check src tests && uv run mypy
git add src/book_ingestion/backends/pdf_docling.py tests/test_pdf_backend_survey.py
git commit -m "feat(pdf): survey() via Docling with chapter map + quality"
```

---

## Task 10: PDF backend — `extract_chapter()`

**Files:**
- Modify: `src/book_ingestion/backends/pdf_docling.py`
- Create: `tests/test_pdf_backend_extract.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the PDF backend's extract_chapter() path."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion.backends.base import Context
from book_ingestion.backends.pdf_docling import PdfDoclingBackend
from book_ingestion.cache import Cache


@pytest.mark.slow
def test_extract_chapter_returns_simple_view(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    backend = PdfDoclingBackend()
    ctx = Context(cache=Cache(root=tmp_cache_dir))
    survey = backend.survey(synthetic_pdf, ctx=ctx)

    if not survey.chapters:
        pytest.skip("Docling found no chapters in the synthetic PDF; covered by real-book test")

    content = backend.extract_chapter(synthetic_pdf, 0, ctx=ctx)
    assert content.chapter.index == 0
    assert content.quality.backend == "docling_pdf"
    # Some blocks should have been produced — at least one paragraph-ish item.
    types = {b.type for b in content.simple_view}
    assert types - {"page_break"}, "no content blocks produced"


@pytest.mark.slow
def test_extract_chapter_index_out_of_range_raises(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    backend = PdfDoclingBackend()
    ctx = Context(cache=Cache(root=tmp_cache_dir))
    backend.survey(synthetic_pdf, ctx=ctx)

    with pytest.raises(IndexError):
        backend.extract_chapter(synthetic_pdf, 9999, ctx=ctx)
```

Save as `tests/test_pdf_backend_extract.py`.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_pdf_backend_extract.py -v -m slow
```
Expected: AttributeError on `extract_chapter`.

- [ ] **Step 3: Add `extract_chapter` to `PdfDoclingBackend`**

Append the following methods inside the `PdfDoclingBackend` class in
`src/book_ingestion/backends/pdf_docling.py`:

```python
    # --- extract ----------------------------------------------------------

    def extract_chapter(self, path: Path, chapter_index: int, *, ctx: Context) -> ChapterContent:
        if ctx.use_cache:
            cached = ctx.cache.read(path, f"chapter-{chapter_index}.json")
            if cached is not None:
                return ChapterContent.model_validate(cached)

        survey = self.survey(path, ctx=ctx)
        if chapter_index < 0 or chapter_index >= len(survey.chapters):
            raise IndexError(
                f"chapter_index {chapter_index} out of range "
                f"(book has {len(survey.chapters)} chapters)"
            )

        chapter = survey.chapters[chapter_index]
        docling_payload = self._get_or_run_docling(path, ctx=ctx)
        assert isinstance(chapter.locator, PageRange)
        items = self._slice_to_items(docling_payload["document"], chapter.locator)
        blocks = project_to_simple_view(items)

        pages_processed = list(range(chapter.locator.start_page, chapter.locator.end_page + 1))
        pages_with_failures = sorted({b.page for b in blocks if b.type == "failed_region" and b.page is not None})
        counts: dict[str, int] = {}
        for b in blocks:
            if hasattr(b, "confidence"):
                key = getattr(b, "confidence").value  # type: ignore[attr-defined]
                counts[key] = counts.get(key, 0) + 1

        # Slice the cached docling.json subtree by page range for the audit pointer.
        chapter_path = self._write_chapter_slice(path, ctx=ctx, chapter_index=chapter_index, locator=chapter.locator)

        content = ChapterContent(
            schema_version=SCHEMA_VERSION,
            source=survey.source,
            chapter=chapter,
            simple_view=blocks,
            quality=Quality(
                backend=self.name,
                pages_processed=pages_processed,
                pages_with_failures=pages_with_failures,
                block_confidence_counts=counts,
                flags=[],
            ),
            cache_paths={"docling_chapter": str(chapter_path)},
        )
        ctx.cache.write(path, f"chapter-{chapter_index}.json", content.model_dump(mode="json"))
        return content

    @staticmethod
    def _slice_to_items(doc_dict: dict[str, Any], locator: "PageRange") -> list["DoclingItem"]:
        """Adapt DoclingDocument JSON items within the locator's page range
        into a list of `DoclingItem`s in reading order."""
        items: list[DoclingItem] = []
        for entry in doc_dict.get("texts") or []:
            prov = entry.get("prov") or []
            page = int(prov[0]["page_no"]) if prov and "page_no" in prov[0] else 0
            if page < locator.start_page or page > locator.end_page:
                continue
            label = str(entry.get("label") or "").lower()
            text = str(entry.get("text") or "")
            score = float(entry.get("confidence") or 0.95)
            kind: ItemKind
            extra: dict[str, Any] = {}
            if "section_header" in label or "heading" in label:
                kind = "heading"
                extra["level"] = int(entry.get("level") or 1)
            elif "list_item" in label:
                kind = "list_item"
                extra["list_marker"] = entry.get("marker")
            elif "footnote" in label:
                kind = "footnote"
                extra["fn_id"] = entry.get("self_ref") or f"fn-{len(items)}"
            elif "caption" in label:
                kind = "figure_caption"
            else:
                kind = "paragraph"
            items.append(DoclingItem(kind=kind, text=text, page=page, score=score, extra=extra))

        for entry in doc_dict.get("tables") or []:
            prov = entry.get("prov") or []
            page = int(prov[0]["page_no"]) if prov and "page_no" in prov[0] else 0
            if page < locator.start_page or page > locator.end_page:
                continue
            rows = _table_rows_from_docling(entry)
            raw_text = "\n".join(" | ".join(r) for r in rows) if rows else ""
            score = float(entry.get("confidence") or 0.80)
            items.append(
                DoclingItem(
                    kind="table",
                    text="",
                    page=page,
                    score=score,
                    extra={"rows": rows, "raw_text": raw_text},
                )
            )

        items.sort(key=lambda it: it.page)
        return items

    def _write_chapter_slice(
        self,
        path: Path,
        *,
        ctx: Context,
        chapter_index: int,
        locator: "PageRange",
    ) -> Path:
        """Write a small JSON file recording the chapter's page range; consumers
        wanting deeper structure can subset the full docling.json themselves."""
        payload = {
            "chapter_index": chapter_index,
            "start_page": locator.start_page,
            "end_page": locator.end_page,
        }
        return ctx.cache.write(path, f"chapter-{chapter_index}.docling.json", payload)


def _table_rows_from_docling(table_entry: dict[str, Any]) -> list[list[str]]:
    """Pull a 2D list of strings from a DoclingDocument table entry."""
    data = table_entry.get("data") or {}
    grid = data.get("grid") or []
    rows: list[list[str]] = []
    for row in grid:
        rows.append([str(cell.get("text") or "") for cell in row])
    return rows
```

Add the imports at the top of the file:

```python
from book_ingestion.ir import (
    SCHEMA_VERSION,
    BookSurvey,
    ChapterContent,
    Confidence,
    PageRange,
    Quality,
    Source,
)
from book_ingestion.projection.to_simple_view import (
    DoclingItem,
    ItemKind,
    project_to_simple_view,
)
```

(Replace the existing `from book_ingestion.ir import ...` line with the expanded form.)

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_pdf_backend_extract.py -v -m slow
```
Expected: 2 passed (or `synthetic_pdf` chapter test skipped if Docling produced no chapters; that's acceptable — the real book test covers it).

- [ ] **Step 5: Run ruff + mypy and commit**

```bash
uv run ruff check src tests && uv run mypy
git add src/book_ingestion/backends/pdf_docling.py tests/test_pdf_backend_extract.py
git commit -m "feat(pdf): extract_chapter() with chapter slicing and projection"
```

---

## Task 11: Public API (`api.py`)

**Files:**
- Create: `src/book_ingestion/api.py`
- Modify: `src/book_ingestion/__init__.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the public API."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion import extract_chapter, survey
from book_ingestion.ir import BookSurvey, ChapterContent


@pytest.mark.slow
def test_survey_public(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    s = survey(synthetic_pdf, cache_dir=tmp_cache_dir)
    assert isinstance(s, BookSurvey)
    assert s.source.format == "pdf"


@pytest.mark.slow
def test_extract_chapter_public(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    s = survey(synthetic_pdf, cache_dir=tmp_cache_dir)
    if not s.chapters:
        pytest.skip("Docling produced no chapters on the synthetic PDF.")
    c = extract_chapter(synthetic_pdf, 0, cache_dir=tmp_cache_dir)
    assert isinstance(c, ChapterContent)
    assert c.chapter.index == 0


def test_survey_rejects_unsupported_format(tmp_path: Path, tmp_cache_dir: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_bytes(b"plain")
    with pytest.raises(ValueError, match="unsupported format"):
        survey(p, cache_dir=tmp_cache_dir)
```

Save as `tests/test_api.py`.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_api.py -v
```
Expected: ImportError on `from book_ingestion import survey, extract_chapter`.

- [ ] **Step 3: Implement `src/book_ingestion/api.py`**

```python
"""Public API surface.

`survey()` and `extract_chapter()` are the only library entry points. Both
are deterministic given the same input and cache state.
"""
from __future__ import annotations

from pathlib import Path

from book_ingestion.backends.base import Backend, Context
from book_ingestion.backends.pdf_docling import PdfDoclingBackend
from book_ingestion.cache import Cache
from book_ingestion.detect import detect_format
from book_ingestion.ir import BookSurvey, ChapterContent

_BACKENDS: dict[str, Backend] = {
    "pdf": PdfDoclingBackend(),
    # "epub": EpubBackend(),     # M2
    # "pdf_ocr": OcrBackend(),   # M3
}


def _backend_for(path: Path) -> Backend:
    fmt = detect_format(path)
    if fmt not in _BACKENDS:
        raise ValueError(f"no backend registered for format: {fmt}")
    return _BACKENDS[fmt]


def survey(
    path: Path,
    *,
    cache_dir: Path | None = None,
    use_cache: bool = True,
    llm_assist: bool = False,
) -> BookSurvey:
    """Produce a BookSurvey for `path`. See spec §3.1."""
    backend = _backend_for(path)
    ctx = Context(cache=Cache(root=cache_dir), use_cache=use_cache, llm_assist=llm_assist)
    return backend.survey(path, ctx=ctx)


def extract_chapter(
    path: Path,
    chapter_index: int,
    *,
    cache_dir: Path | None = None,
    use_cache: bool = True,
) -> ChapterContent:
    """Produce a ChapterContent for chapter `chapter_index` of `path`. See spec §3.2."""
    backend = _backend_for(path)
    ctx = Context(cache=Cache(root=cache_dir), use_cache=use_cache)
    return backend.extract_chapter(path, chapter_index, ctx=ctx)
```

- [ ] **Step 4: Update `src/book_ingestion/__init__.py` to re-export**

Replace the existing file content with:

```python
"""book_ingestion — turn a book into a JSON IR."""

from book_ingestion.api import extract_chapter, survey
from book_ingestion.ir import (
    SCHEMA_VERSION,
    BookSurvey,
    ChapterContent,
)

__version__ = "0.1.0"

__all__ = [
    "SCHEMA_VERSION",
    "BookSurvey",
    "ChapterContent",
    "__version__",
    "extract_chapter",
    "survey",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_api.py -v
```
Expected: 1 passed (the `test_survey_rejects_unsupported_format` fast test), 2 passed when run with `-m slow`.

- [ ] **Step 6: Run ruff + mypy and commit**

```bash
uv run ruff check src tests && uv run mypy
git add src/book_ingestion/api.py src/book_ingestion/__init__.py tests/test_api.py
git commit -m "feat(api): public survey() and extract_chapter() entry points"
```

---

## Task 12: CLI (Typer app)

**Files:**
- Create: `src/book_ingestion/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the CLI."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from book_ingestion.cli import app


runner = CliRunner()


def test_cli_rejects_unsupported_format(tmp_path: Path, tmp_cache_dir: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_bytes(b"hello")
    result = runner.invoke(app, ["survey", str(p), "--cache-dir", str(tmp_cache_dir)])
    assert result.exit_code == 1
    # Error JSON on stderr
    assert "unsupported format" in (result.stderr or result.output)


@pytest.mark.slow
def test_cli_survey_emits_valid_json(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    result = runner.invoke(
        app, ["survey", str(synthetic_pdf), "--cache-dir", str(tmp_cache_dir)]
    )
    assert result.exit_code in (0, 2), result.output
    payload = json.loads(result.output)
    assert payload["kind"] == "book_survey"
    assert payload["schema_version"] == "1.0"


def test_cli_missing_file_exits_one(tmp_cache_dir: Path) -> None:
    result = runner.invoke(
        app, ["survey", "/no/such/file.pdf", "--cache-dir", str(tmp_cache_dir)]
    )
    assert result.exit_code == 1


def test_cli_json_schema_subcommand_emits_schema() -> None:
    result = runner.invoke(app, ["--json-schema", "survey"])
    assert result.exit_code == 0
    schema = json.loads(result.output)
    assert "properties" in schema
    assert schema["properties"]["kind"]["const"] == "book_survey"
```

Save as `tests/test_cli.py`.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest tests/test_cli.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement `src/book_ingestion/cli.py`**

```python
"""Typer-based CLI: book-ingest survey | extract | cache.

JSON to stdout. Logs and errors to stderr. Exit codes:
  0 — success
  2 — extraction refused (degraded JSON still emitted)
  1 — hard error
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import typer

from book_ingestion import extract_chapter, survey
from book_ingestion.cache import Cache, default_cache_root
from book_ingestion.ir import BookSurvey, ChapterContent
from book_ingestion.detect import detect_format

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
cache_app = typer.Typer(help="Cache management")
app.add_typer(cache_app, name="cache")


def _print_json(payload: dict) -> None:
    """Write a JSON payload to stdout without trailing newline jitter."""
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def _err(msg: str, kind: str = "error") -> None:
    sys.stderr.write(json.dumps({"error": msg, "type": kind}) + "\n")


def _refused(s: BookSurvey | ChapterContent) -> bool:
    """Does this payload represent extraction-refused (exit code 2)?"""
    if isinstance(s, BookSurvey):
        return s.map.provenance.value == "none" or "unparseable" in s.quality.flags
    # ChapterContent: refused when every block is failed_region.
    return bool(s.simple_view) and all(b.type == "failed_region" for b in s.simple_view)


def _configure_logging(quiet: bool, verbose: bool) -> None:
    level = logging.WARNING
    if verbose:
        level = logging.INFO
    if quiet:
        level = logging.ERROR
    logging.basicConfig(level=level, stream=sys.stderr, format="%(message)s")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    json_schema: Optional[str] = typer.Option(
        None, "--json-schema", help="Emit JSON schema for 'survey' or 'extract' and exit."
    ),
) -> None:
    """book-ingest — turn a book into a JSON IR."""
    if json_schema is not None:
        if json_schema == "survey":
            _print_json(BookSurvey.model_json_schema())
        elif json_schema == "extract":
            _print_json(ChapterContent.model_json_schema())
        else:
            _err(f"unknown schema name: {json_schema}", kind="usage")
            raise typer.Exit(1)
        raise typer.Exit(0)


@app.command("survey")
def cmd_survey(
    path: Path = typer.Argument(..., exists=False),
    cache_dir: Path = typer.Option(default_cache_root(), "--cache-dir"),
    no_cache: bool = typer.Option(False, "--no-cache"),
    llm_assist: bool = typer.Option(False, "--llm-assist"),
    quiet: bool = typer.Option(False, "--quiet"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    _configure_logging(quiet, verbose)
    try:
        if not path.exists():
            _err(f"file not found: {path}", kind="not_found")
            raise typer.Exit(1)
        _ = detect_format(path)  # rejects unsupported formats early with ValueError
        s = survey(path, cache_dir=cache_dir, use_cache=not no_cache, llm_assist=llm_assist)
    except ValueError as e:
        _err(str(e), kind="value_error")
        raise typer.Exit(1) from e
    except Exception as e:  # noqa: BLE001 — boundary handler
        _err(str(e), kind=type(e).__name__)
        raise typer.Exit(1) from e
    _print_json(s.model_dump(mode="json"))
    raise typer.Exit(2 if _refused(s) else 0)


@app.command("extract")
def cmd_extract(
    path: Path = typer.Argument(..., exists=False),
    chapter: int = typer.Option(..., "--chapter", "-c"),
    cache_dir: Path = typer.Option(default_cache_root(), "--cache-dir"),
    no_cache: bool = typer.Option(False, "--no-cache"),
    quiet: bool = typer.Option(False, "--quiet"),
    verbose: bool = typer.Option(False, "--verbose"),
) -> None:
    _configure_logging(quiet, verbose)
    try:
        if not path.exists():
            _err(f"file not found: {path}", kind="not_found")
            raise typer.Exit(1)
        _ = detect_format(path)
        c = extract_chapter(path, chapter, cache_dir=cache_dir, use_cache=not no_cache)
    except IndexError as e:
        _err(str(e), kind="index_error")
        raise typer.Exit(1) from e
    except ValueError as e:
        _err(str(e), kind="value_error")
        raise typer.Exit(1) from e
    except Exception as e:  # noqa: BLE001
        _err(str(e), kind=type(e).__name__)
        raise typer.Exit(1) from e
    _print_json(c.model_dump(mode="json"))
    raise typer.Exit(2 if _refused(c) else 0)


@cache_app.command("list")
def cmd_cache_list(
    cache_dir: Path = typer.Option(default_cache_root(), "--cache-dir"),
) -> None:
    if not cache_dir.exists():
        _print_json({"entries": []})
        return
    entries = [d.name for d in cache_dir.iterdir() if d.is_dir()]
    _print_json({"entries": entries})


@cache_app.command("clear")
def cmd_cache_clear(
    path: Optional[Path] = typer.Argument(None),
    all_: bool = typer.Option(False, "--all"),
    cache_dir: Path = typer.Option(default_cache_root(), "--cache-dir"),
) -> None:
    if all_:
        if cache_dir.exists():
            for d in cache_dir.iterdir():
                if d.is_dir():
                    for p in d.iterdir():
                        p.unlink()
                    d.rmdir()
        _print_json({"cleared": "all"})
        return
    if path is None:
        _err("provide a path or --all", kind="usage")
        raise typer.Exit(1)
    cache = Cache(root=cache_dir)
    cache.clear(path)
    _print_json({"cleared": str(path)})
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
uv run pytest tests/test_cli.py -v
```
Expected: at least the 3 fast tests pass; the slow one passes under `-m slow`.

- [ ] **Step 5: Verify the entry point works**

Run:
```bash
uv run book-ingest --help
```
Expected: usage text listing `survey`, `extract`, `cache` subcommands.

- [ ] **Step 6: Run ruff + mypy and commit**

```bash
uv run ruff check src tests && uv run mypy
git add src/book_ingestion/cli.py tests/test_cli.py
git commit -m "feat(cli): Typer app with survey/extract/cache, JSON-to-stdout, exit codes"
```

---

## Task 13: End-to-end acceptance on the real test book

**Files:**
- Create: `tests/test_pdf_real.py`

This test exercises the full stack on `test/What is Modern Israel (Yakov M. Rabkin) (z-library.sk, 1lib.sk, z-lib.sk).pdf`. It is marked `slow` and `real_book` — runs on demand, not on every commit. The acceptance bar is structural (chapter map populated, blocks produced, sensible quality flags), not exact-text — real OCR and layout outputs vary by Docling version.

- [ ] **Step 1: Write the acceptance test**

```python
"""End-to-end acceptance test against the real book in test/."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion import extract_chapter, survey
from book_ingestion.ir import Confidence, Provenance

BOOK = Path(__file__).parent.parent / "test" / "What is Modern Israel (Yakov M. Rabkin) (z-library.sk, 1lib.sk, z-lib.sk).pdf"


pytestmark = [pytest.mark.slow, pytest.mark.real_book]


def _has_book() -> bool:
    return BOOK.exists()


@pytest.mark.skipif(not _has_book(), reason="real book file not present at test/")
def test_survey_returns_valid_book_survey(tmp_cache_dir: Path) -> None:
    s = survey(BOOK, cache_dir=tmp_cache_dir)
    assert s.kind == "book_survey"
    assert s.source.format == "pdf"
    assert s.source.size_bytes > 100_000  # 4.5MB book
    assert s.quality.pages_total is not None and s.quality.pages_total > 100
    # Provenance must be one of the four
    assert s.map.provenance in {
        Provenance.EMBEDDED,
        Provenance.INFERRED,
        Provenance.LLM_ASSISTED,
        Provenance.NONE,
    }


@pytest.mark.skipif(not _has_book(), reason="real book file not present at test/")
def test_extract_each_detected_chapter(tmp_cache_dir: Path) -> None:
    s = survey(BOOK, cache_dir=tmp_cache_dir)
    if not s.chapters:
        pytest.skip(f"no chapters detected (map.provenance={s.map.provenance.value})")

    for chapter in s.chapters:
        c = extract_chapter(BOOK, chapter.index, cache_dir=tmp_cache_dir)
        assert c.chapter.index == chapter.index
        # Pages processed cover the chapter's locator range.
        from book_ingestion.ir import PageRange
        assert isinstance(chapter.locator, PageRange)
        assert min(c.quality.pages_processed) >= chapter.locator.start_page
        assert max(c.quality.pages_processed) <= chapter.locator.end_page
        # We produced *some* non-page-break block.
        non_break = [b for b in c.simple_view if b.type != "page_break"]
        assert non_break, f"chapter {chapter.index} produced no content blocks"
        # Quality grade tracks Docling's report.
        for grade_field in ("docling_mean_grade", "docling_low_grade"):
            v = getattr(s.quality, grade_field)
            assert v is None or isinstance(v, Confidence)
```

Save as `tests/test_pdf_real.py`.

- [ ] **Step 2: Run the acceptance test**

Run:
```bash
uv run pytest tests/test_pdf_real.py -v -m slow
```

Expected, on the real book:
- both tests pass
- runtime in the order of a few minutes (Docling parses ~200+ page PDFs in single-digit-minutes on CPU)

If `survey` returns `map.provenance == "none"` and skips the second test:
- inspect `cache_paths.docling_document` to see what Docling's outline/section structure looks like for this book
- update `PdfDoclingBackend._extract_heading_hints` to use the correct label/level path
- re-run

This is the principal verification feedback loop for M1.

- [ ] **Step 3: Manual acceptance review**

Run end-to-end CLI commands and manually review the output:

```bash
uv run book-ingest survey "test/What is Modern Israel (Yakov M. Rabkin) (z-library.sk, 1lib.sk, z-lib.sk).pdf" > /tmp/survey.json
cat /tmp/survey.json | python -m json.tool | less
```

Check by eye:
- Chapter titles in `chapters[*].title` look right against the book's actual TOC.
- Page ranges look plausible (no chapter spans the whole book; no zero-length chapters).
- `quality.flags` contains `embedded_toc_present` (if Docling found the outline) or `toc_inferred` / `toc_unresolved` (otherwise).
- `map.provenance` matches the detection method.

Then for one chapter:
```bash
uv run book-ingest extract "test/What is Modern Israel (Yakov M. Rabkin) (z-library.sk, 1lib.sk, z-lib.sk).pdf" --chapter 0 > /tmp/ch0.json
cat /tmp/ch0.json | python -m json.tool | less
```

Check by eye:
- First few `simple_view` blocks: the heading is the chapter title; subsequent paragraphs are the chapter's actual opening prose.
- No `failed_region` blocks unless the source page in the PDF is visibly defective.
- `quality.block_confidence_counts` is dominated by EXCELLENT/GOOD.

- [ ] **Step 4: Commit**

```bash
git add tests/test_pdf_real.py
git commit -m "test: end-to-end acceptance on the real book in test/"
```

---

## End-of-M1 checklist

Before declaring M1 done, verify:

- [ ] `uv run pytest` (fast tests only) passes with zero failures.
- [ ] `uv run pytest -m slow` (integration) passes — including `test_pdf_real.py`.
- [ ] `uv run ruff check src tests` clean.
- [ ] `uv run mypy` clean.
- [ ] Manual acceptance review of the test book passes (Task 13 Step 3).
- [ ] CLI `book-ingest survey --help` and `book-ingest extract --help` produce usable help text.
- [ ] One survey + one extract has been run end-to-end on the real test book and the JSON has been spot-checked.

Once all boxes are ticked, tag the milestone:

```bash
git tag -a v0.1.0-m1 -m "M1 — PDF MVP via Docling"
```

Then proceed to M2 planning (EPUB backend) using the same `writing-plans` flow against the design spec's §5.4.
