# `extract_metadata` M2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fast, public `extract_metadata(path, *, pages=6) -> BookMetadata` function to `book-ingestion` that returns frontmatter-shaped book metadata for PDFs (pypdf) and EPUBs (stdlib `zipfile` + `xml.etree`), with zero new runtime dependencies.

**Architecture:** New `MetadataExtractor` Protocol mirroring the existing `Backend` Protocol, with two implementations (`PdfMetadataExtractor`, `EpubMetadataExtractor`) dispatched via `detect_format`. New typed `BookMetadata` model in `metadata.py`. No Docling on this path. No caching.

**Tech Stack:** Python 3.11+, Pydantic v2, pypdf (already a dep), stdlib `zipfile` / `xml.etree.ElementTree`, pytest + reportlab (dev) for fixtures.

**Spec:** [`../specs/2026-05-13-extract-metadata-design.md`](../specs/2026-05-13-extract-metadata-design.md)
**Cross-agent thread:** `.cowork/archive/0001…0006`, `.cowork/inbox/0007`

---

## Conventions for this plan

- Run tests via `uv run pytest`. Project is `uv`-managed.
- Markers in `pyproject.toml`: `slow` (deselect with `-m "not slow"`), `real_book`.
- `mypy --strict` over `src/book_ingestion/`. Type-check after every implementation task.
- `ruff check src tests` after every task.
- Each task ends with a commit. Use conventional-commits prefixes (`feat:`, `test:`, `refactor:`, `fix:`, `chore:`).
- Commit message in heredoc form (matches repo convention):
  ```bash
  git commit -m "$(cat <<'EOF'
  feat(metadata): one-line summary

  Longer body if useful.

  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  EOF
  )"
  ```

---

## File map

### New files

| Path | Purpose |
|---|---|
| `src/book_ingestion/metadata.py` | `BookMetadata` + sub-models + closed-vocab enums + ISBN/edition helper functions |
| `src/book_ingestion/extractors/__init__.py` | Empty package marker |
| `src/book_ingestion/extractors/base.py` | `MetadataExtractor` Protocol |
| `src/book_ingestion/extractors/pdf.py` | `PdfMetadataExtractor` — pypdf-based |
| `src/book_ingestion/extractors/epub.py` | `EpubMetadataExtractor` — stdlib zipfile + xml.etree |
| `tests/fixtures/__init__.py` | Empty package marker |
| `tests/fixtures/pdf.py` | reportlab helpers for synthetic PDF fixtures |
| `tests/fixtures/epub.py` | stdlib helpers for synthetic EPUB fixtures |
| `tests/test_metadata_model.py` | Pydantic model tests for `BookMetadata` and sub-models |
| `tests/test_metadata_isbn.py` | ISBN helpers (canonicalize, isbn10→isbn13, dedupe) |
| `tests/test_metadata_edition.py` | Edition hint classification + priority |
| `tests/test_metadata_pdf.py` | `PdfMetadataExtractor` unit + synthetic-fixture tests |
| `tests/test_metadata_epub.py` | `EpubMetadataExtractor` unit + synthetic-fixture tests |
| `tests/test_metadata_api.py` | Public `extract_metadata` dispatch tests |
| `tests/test_metadata_real.py` | `@slow @real_book` acceptance tests for the two real fixtures |

### Modified files

| Path | Change |
|---|---|
| `src/book_ingestion/api.py` | Add `extract_metadata()` function + `_EXTRACTORS` registry |
| `src/book_ingestion/__init__.py` | Re-export `extract_metadata` and `BookMetadata` |

---

## Task overview

| # | Task | Files (primary) |
|---|---|---|
| 1 | Skeleton modules + smoke test | `metadata.py`, `extractors/{__init__,base}.py`, `tests/test_metadata_model.py` |
| 2 | Closed-vocab enums | `metadata.py`, `tests/test_metadata_model.py` |
| 3 | Sub-models (Identifier*, Creator, MetadataWarning) | `metadata.py`, `tests/test_metadata_model.py` |
| 4 | `BookMetadata` top-level model | `metadata.py`, `tests/test_metadata_model.py` |
| 5 | ISBN helpers (canonicalize, isbn10→isbn13, dedupe) | `metadata.py`, `tests/test_metadata_isbn.py` |
| 6 | Edition hint classification + priority | `metadata.py`, `tests/test_metadata_edition.py` |
| 7 | PDF fixture helpers (reportlab) | `tests/fixtures/{__init__,pdf}.py` |
| 8 | PDF extractor: encryption + no-text paths | `extractors/pdf.py`, `tests/test_metadata_pdf.py` |
| 9 | PDF: identifier extraction (DOI/arXiv/ISBN + dedupe) | `extractors/pdf.py`, `tests/test_metadata_pdf.py` |
| 10 | PDF: title / subtitle | `extractors/pdf.py`, `tests/test_metadata_pdf.py` |
| 11 | PDF: creators | `extractors/pdf.py`, `tests/test_metadata_pdf.py` |
| 12 | PDF: publisher / places / date / edition | `extractors/pdf.py`, `tests/test_metadata_pdf.py` |
| 13 | EPUB fixture helpers (stdlib) | `tests/fixtures/epub.py` |
| 14 | EPUB extractor: DRM + malformed paths | `extractors/epub.py`, `tests/test_metadata_epub.py` |
| 15 | EPUB: OPF basics (title, publisher, language) | `extractors/epub.py`, `tests/test_metadata_epub.py` |
| 16 | EPUB: creators | `extractors/epub.py`, `tests/test_metadata_epub.py` |
| 17 | EPUB: identifier (urn:isbn, meta isbn/eisbn) | `extractors/epub.py`, `tests/test_metadata_epub.py` |
| 18 | EPUB: date selection | `extractors/epub.py`, `tests/test_metadata_epub.py` |
| 19 | EPUB: title-page xhtml fallback | `extractors/epub.py`, `tests/test_metadata_epub.py` |
| 20 | Public `extract_metadata` + dispatch + re-exports | `api.py`, `__init__.py`, `tests/test_metadata_api.py` |
| 21 | Real-fixture acceptance: Holocaust Industry PDF | `tests/test_metadata_real.py` |
| 22 | Real-fixture acceptance: Gaza EPUB | `tests/test_metadata_real.py` |

---

## Task 1: Skeleton modules + smoke test

**Goal:** Create empty `metadata.py` and `extractors/` package so subsequent tasks have somewhere to write.

**Files:**
- Create: `src/book_ingestion/metadata.py`
- Create: `src/book_ingestion/extractors/__init__.py`
- Create: `src/book_ingestion/extractors/base.py`
- Create: `tests/test_metadata_model.py`

- [ ] **Step 1: Write failing smoke test**

In `tests/test_metadata_model.py`:

```python
"""Tests for the BookMetadata Pydantic model and its sub-models."""
from __future__ import annotations


def test_imports() -> None:
    from book_ingestion import metadata  # noqa: F401
    from book_ingestion.extractors import base  # noqa: F401
```

- [ ] **Step 2: Run test, expect ImportError**

```bash
uv run pytest tests/test_metadata_model.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'book_ingestion.metadata'`.

- [ ] **Step 3: Create skeleton files**

`src/book_ingestion/metadata.py`:

```python
"""Book metadata schema and helpers.

Returned by `book_ingestion.extract_metadata()`. See
`docs/superpowers/specs/2026-05-13-extract-metadata-design.md` for the full
shape and contract.
"""
from __future__ import annotations
```

`src/book_ingestion/extractors/__init__.py`:

```python
```

(Empty package marker — one newline only, no docstring.)

`src/book_ingestion/extractors/base.py`:

```python
"""MetadataExtractor Protocol — see docs/superpowers/specs/2026-05-13-extract-metadata-design.md §2.

Each format gets one extractor. Backends remain separate (in `backends/`)
and are used for the heavyweight IR path; metadata extractors are
lightweight, no caching, no Docling.
"""
from __future__ import annotations
```

- [ ] **Step 4: Run smoke test, expect pass**

```bash
uv run pytest tests/test_metadata_model.py -v
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/metadata.py src/book_ingestion/extractors/ tests/test_metadata_model.py
git commit -m "$(cat <<'EOF'
chore(metadata): skeleton modules for M2.0 extract_metadata

Empty package markers and module docstrings. Subsequent tasks fill in
BookMetadata, sub-models, helpers, and per-format extractors.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Closed-vocab enums

**Goal:** Add the five `StrEnum`s from spec §4.1.

**Files:**
- Modify: `src/book_ingestion/metadata.py`
- Modify: `tests/test_metadata_model.py`

- [ ] **Step 1: Write failing enum tests**

Append to `tests/test_metadata_model.py`:

```python
from book_ingestion.metadata import (
    CreatorRole,
    EditionHint,
    ErrorCode,
    IdentifierKind,
    WarningCode,
)


def test_identifier_kind_members() -> None:
    assert {k.value for k in IdentifierKind} == {"isbn", "doi", "arxiv"}


def test_edition_hint_members() -> None:
    assert {e.value for e in EditionHint} == {
        "paperback",
        "hardback",
        "ebook",
        "unspecified",
    }


def test_creator_role_members() -> None:
    assert {r.value for r in CreatorRole} == {
        "author",
        "editor",
        "translator",
        "foreword",
        "illustrator",
    }


def test_error_code_members() -> None:
    assert {e.value for e in ErrorCode} == {
        "encrypted",
        "drm_protected",
        "malformed_pdf",
        "malformed_epub",
    }


def test_warning_code_members() -> None:
    assert {w.value for w in WarningCode} == {
        "title_all_caps_in_source",
        "subtitle_not_in_opf",
        "multiple_isbns_detected",
        "dc_creator_trailing_punctuation",
        "language_normalised",
        "no_text_extracted",
        "incomplete_extraction",
        "multiple_places_detected",
    }
```

- [ ] **Step 2: Run, expect ImportError**

```bash
uv run pytest tests/test_metadata_model.py -v
```

Expected: FAIL — `ImportError: cannot import name 'CreatorRole' from 'book_ingestion.metadata'`.

- [ ] **Step 3: Add enums**

Append to `src/book_ingestion/metadata.py`:

```python
from enum import StrEnum


class IdentifierKind(StrEnum):
    ISBN = "isbn"
    DOI = "doi"
    ARXIV = "arxiv"


class EditionHint(StrEnum):
    PAPERBACK = "paperback"
    HARDBACK = "hardback"
    EBOOK = "ebook"
    UNSPECIFIED = "unspecified"


class CreatorRole(StrEnum):
    AUTHOR = "author"
    EDITOR = "editor"
    TRANSLATOR = "translator"
    FOREWORD = "foreword"
    ILLUSTRATOR = "illustrator"


class ErrorCode(StrEnum):
    ENCRYPTED = "encrypted"
    DRM_PROTECTED = "drm_protected"
    MALFORMED_PDF = "malformed_pdf"
    MALFORMED_EPUB = "malformed_epub"


class WarningCode(StrEnum):
    TITLE_ALL_CAPS_IN_SOURCE = "title_all_caps_in_source"
    SUBTITLE_NOT_IN_OPF = "subtitle_not_in_opf"
    MULTIPLE_ISBNS_DETECTED = "multiple_isbns_detected"
    DC_CREATOR_TRAILING_PUNCTUATION = "dc_creator_trailing_punctuation"
    LANGUAGE_NORMALISED = "language_normalised"
    NO_TEXT_EXTRACTED = "no_text_extracted"
    INCOMPLETE_EXTRACTION = "incomplete_extraction"
    MULTIPLE_PLACES_DETECTED = "multiple_places_detected"
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_model.py -v
```

Expected: PASS (6 tests including the smoke test).

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/metadata.py tests/test_metadata_model.py
git commit -m "$(cat <<'EOF'
feat(metadata): closed-vocab enums for identifier, edition, role, error, warning

Five StrEnums defining the closed vocabularies referenced in the
extract_metadata spec §4.1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Sub-models — `IdentifierCandidate`, `Identifier`, `Creator`, `MetadataWarning`

**Goal:** Add the four sub-models from spec §4.2. All `frozen=True`.

**Files:**
- Modify: `src/book_ingestion/metadata.py`
- Modify: `tests/test_metadata_model.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_model.py`:

```python
from book_ingestion.metadata import (
    Creator,
    Identifier,
    IdentifierCandidate,
    MetadataWarning,
)


def test_identifier_candidate_defaults() -> None:
    c = IdentifierCandidate(kind=IdentifierKind.ISBN, value="9781844674879")
    assert c.kind == IdentifierKind.ISBN
    assert c.value == "9781844674879"
    assert c.edition_hint == EditionHint.UNSPECIFIED


def test_identifier_candidate_frozen() -> None:
    import pydantic
    c = IdentifierCandidate(kind=IdentifierKind.ISBN, value="9781844674879")
    with pytest.raises(pydantic.ValidationError):
        c.value = "other"  # type: ignore[misc]


def test_identifier_defaults() -> None:
    i = Identifier()
    assert i.kind is None
    assert i.value is None
    assert i.candidates == []


def test_creator_defaults() -> None:
    c = Creator()
    assert c.role == CreatorRole.AUTHOR
    assert c.first_name is None
    assert c.last_name is None
    assert c.raw is None


def test_creator_with_fields() -> None:
    c = Creator(
        role=CreatorRole.TRANSLATOR,
        first_name="Norman G.",
        last_name="Finkelstein",
        raw="Finkelstein, Norman; ",
    )
    assert c.last_name == "Finkelstein"
    assert c.raw == "Finkelstein, Norman; "


def test_metadata_warning() -> None:
    w = MetadataWarning(code=WarningCode.LANGUAGE_NORMALISED, detail="en-US -> en")
    assert w.code == WarningCode.LANGUAGE_NORMALISED
    assert w.detail == "en-US -> en"


def test_metadata_warning_no_detail() -> None:
    w = MetadataWarning(code=WarningCode.SUBTITLE_NOT_IN_OPF)
    assert w.detail is None
```

Also add `import pytest` at the top if not already present.

- [ ] **Step 2: Run, expect ImportError**

```bash
uv run pytest tests/test_metadata_model.py -v
```

Expected: FAIL — `ImportError: cannot import name 'IdentifierCandidate'`.

- [ ] **Step 3: Add sub-models**

Append to `src/book_ingestion/metadata.py`:

```python
from pydantic import BaseModel, ConfigDict, Field


class IdentifierCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: IdentifierKind
    value: str
    edition_hint: EditionHint = EditionHint.UNSPECIFIED


class Identifier(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: IdentifierKind | None = None
    value: str | None = None
    candidates: list[IdentifierCandidate] = Field(default_factory=list)


class Creator(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: CreatorRole = CreatorRole.AUTHOR
    first_name: str | None = None
    last_name: str | None = None
    raw: str | None = None


class MetadataWarning(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: WarningCode
    detail: str | None = None
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_model.py -v
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/metadata.py tests/test_metadata_model.py
git commit -m "$(cat <<'EOF'
feat(metadata): sub-models for identifier, creator, warning

Adds IdentifierCandidate, Identifier, Creator, MetadataWarning per
extract_metadata spec §4.2. All frozen=True matching ir.py convention.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `BookMetadata` top-level model + JSON round-trip

**Goal:** Add the top-level `BookMetadata` from spec §4.3. Verify it serialises to JSON matching the skill spec shape.

**Files:**
- Modify: `src/book_ingestion/metadata.py`
- Modify: `tests/test_metadata_model.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_model.py`:

```python
from typing import Literal

from book_ingestion.ir import SCHEMA_VERSION
from book_ingestion.metadata import BookMetadata


def test_book_metadata_defaults() -> None:
    m = BookMetadata()
    assert m.schema_version == SCHEMA_VERSION
    assert m.kind == "book_metadata"
    assert m.title is None
    assert m.creators == []
    assert m.places == []
    assert m.error is None
    assert m.warnings == []
    assert m.identifier.kind is None


def test_book_metadata_full() -> None:
    m = BookMetadata(
        identifier=Identifier(
            kind=IdentifierKind.ISBN,
            value="9781844674879",
            candidates=[
                IdentifierCandidate(
                    kind=IdentifierKind.ISBN,
                    value="9781844674879",
                    edition_hint=EditionHint.PAPERBACK,
                ),
            ],
        ),
        title="The Holocaust Industry",
        subtitle="Reflections on the Exploitation of Jewish Suffering",
        full_title="The Holocaust Industry: Reflections on the Exploitation of Jewish Suffering",
        creators=[Creator(first_name="Norman G.", last_name="Finkelstein")],
        publisher="Verso",
        places=["London", "New York"],
        date="2003",
        first_published="2000",
        edition="Second Paperback Edition",
        language="en",
        warnings=[MetadataWarning(code=WarningCode.TITLE_ALL_CAPS_IN_SOURCE)],
    )
    assert m.identifier.value == "9781844674879"
    assert m.full_title.startswith("The Holocaust Industry:")
    assert m.creators[0].last_name == "Finkelstein"


def test_book_metadata_json_round_trip() -> None:
    m = BookMetadata(
        title="X",
        identifier=Identifier(kind=IdentifierKind.ISBN, value="9780520295711"),
    )
    payload = m.model_dump(mode="json")
    # Spot-check the dict shape:
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["kind"] == "book_metadata"
    assert payload["title"] == "X"
    assert payload["identifier"]["kind"] == "isbn"
    assert payload["identifier"]["value"] == "9780520295711"
    assert payload["warnings"] == []
    assert payload["error"] is None

    again = BookMetadata.model_validate(payload)
    assert again == m


def test_book_metadata_error_excludes_other_fields_at_default() -> None:
    """When error is set, other fields stay at defaults (caller contract)."""
    m = BookMetadata(error=ErrorCode.ENCRYPTED)
    assert m.error == ErrorCode.ENCRYPTED
    assert m.title is None
    assert m.creators == []
    assert m.warnings == []
```

- [ ] **Step 2: Run, expect ImportError**

```bash
uv run pytest tests/test_metadata_model.py -v
```

Expected: FAIL — `ImportError: cannot import name 'BookMetadata'`.

- [ ] **Step 3: Add `BookMetadata`**

Append to `src/book_ingestion/metadata.py`:

```python
from typing import Literal

from book_ingestion.ir import SCHEMA_VERSION


class BookMetadata(BaseModel):
    schema_version: str = SCHEMA_VERSION
    kind: Literal["book_metadata"] = "book_metadata"

    # Identifier
    identifier: Identifier = Field(default_factory=Identifier)

    # Title
    title: str | None = None
    subtitle: str | None = None
    full_title: str | None = None

    # Authorship
    creators: list[Creator] = Field(default_factory=list)

    # Publication
    publisher: str | None = None
    places: list[str] = Field(default_factory=list)
    date: str | None = None
    first_published: str | None = None
    edition: str | None = None

    # Other
    language: str | None = None

    # Diagnostics
    error: ErrorCode | None = None
    warnings: list[MetadataWarning] = Field(default_factory=list)
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_model.py -v
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/metadata.py tests/test_metadata_model.py
git commit -m "$(cat <<'EOF'
feat(metadata): BookMetadata top-level model

Adds BookMetadata per extract_metadata spec §4.3. JSON round-trips
through Pydantic.model_dump(mode="json"). schema_version inherits
from ir.SCHEMA_VERSION (currently 1.1; no bump for M2.0).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: ISBN helpers — canonicalize, ISBN-10 → ISBN-13, dedupe

**Goal:** Three module-level helper functions in `metadata.py` for ISBN handling.

**Files:**
- Modify: `src/book_ingestion/metadata.py`
- Create: `tests/test_metadata_isbn.py`

- [ ] **Step 1: Write failing tests**

`tests/test_metadata_isbn.py`:

```python
"""Tests for ISBN canonicalization, ISBN-10 to ISBN-13 conversion, and dedupe."""
from __future__ import annotations

import pytest

from book_ingestion.metadata import (
    EditionHint,
    IdentifierCandidate,
    IdentifierKind,
    canonicalize_isbn,
    dedupe_isbn_candidates,
    isbn10_to_isbn13,
)


# --- canonicalize_isbn -------------------------------------------------------

def test_canonicalize_strips_hyphens() -> None:
    assert canonicalize_isbn("978-1-84467-487-9") == "9781844674879"


def test_canonicalize_strips_spaces() -> None:
    assert canonicalize_isbn("978 1 84467 487 9") == "9781844674879"


def test_canonicalize_preserves_X() -> None:
    assert canonicalize_isbn("0-306-40615-X") == "030640615X"


def test_canonicalize_isbn10_already_clean() -> None:
    assert canonicalize_isbn("1844674878") == "1844674878"


# --- isbn10_to_isbn13 --------------------------------------------------------

def test_isbn10_to_isbn13_basic() -> None:
    # 1-84467-487-8 (ISBN-10) -> 978-1-84467-487-9 (ISBN-13)
    assert isbn10_to_isbn13("1844674878") == "9781844674879"


def test_isbn10_to_isbn13_check_digit_recompute() -> None:
    # 0-306-40615-2 -> 978-0-306-40615-7 (worked example from ISBN standard)
    assert isbn10_to_isbn13("0306406152") == "9780306406157"


def test_isbn10_to_isbn13_with_X_check_digit() -> None:
    # 0-19-852663-X -> 978-0-19-852663-1
    assert isbn10_to_isbn13("019852663X") == "9780198526631"


def test_isbn10_to_isbn13_rejects_non_isbn10() -> None:
    with pytest.raises(ValueError):
        isbn10_to_isbn13("9781844674879")  # already ISBN-13


# --- dedupe_isbn_candidates --------------------------------------------------

def test_dedupe_collapses_isbn10_and_isbn13_same_book() -> None:
    candidates = [
        IdentifierCandidate(
            kind=IdentifierKind.ISBN,
            value="1844674878",
            edition_hint=EditionHint.PAPERBACK,
        ),
        IdentifierCandidate(
            kind=IdentifierKind.ISBN,
            value="9781844674879",
            edition_hint=EditionHint.PAPERBACK,
        ),
    ]
    deduped = dedupe_isbn_candidates(candidates)
    assert len(deduped) == 1
    assert deduped[0].value == "9781844674879"  # ISBN-13 form wins
    assert deduped[0].edition_hint == EditionHint.PAPERBACK


def test_dedupe_preserves_distinct_editions() -> None:
    candidates = [
        IdentifierCandidate(
            kind=IdentifierKind.ISBN, value="9781844674879", edition_hint=EditionHint.PAPERBACK
        ),
        IdentifierCandidate(
            kind=IdentifierKind.ISBN, value="9781844677115", edition_hint=EditionHint.HARDBACK
        ),
    ]
    deduped = dedupe_isbn_candidates(candidates)
    assert len(deduped) == 2


def test_dedupe_edition_hint_from_isbn13_form_wins_on_conflict() -> None:
    candidates = [
        IdentifierCandidate(
            kind=IdentifierKind.ISBN, value="1844674878", edition_hint=EditionHint.UNSPECIFIED
        ),
        IdentifierCandidate(
            kind=IdentifierKind.ISBN, value="9781844674879", edition_hint=EditionHint.PAPERBACK
        ),
    ]
    deduped = dedupe_isbn_candidates(candidates)
    assert len(deduped) == 1
    assert deduped[0].edition_hint == EditionHint.PAPERBACK
```

- [ ] **Step 2: Run, expect ImportError**

```bash
uv run pytest tests/test_metadata_isbn.py -v
```

Expected: FAIL — `ImportError: cannot import name 'canonicalize_isbn'`.

- [ ] **Step 3: Implement helpers**

Append to `src/book_ingestion/metadata.py`:

```python
import re


_ISBN_SEPARATOR_RE = re.compile(r"[-\s]")


def canonicalize_isbn(raw: str) -> str:
    """Strip separators from an ISBN string, leaving digits (and optional final 'X')."""
    return _ISBN_SEPARATOR_RE.sub("", raw).upper()


def isbn10_to_isbn13(isbn10: str) -> str:
    """Convert a canonicalized 10-digit ISBN to its 13-digit form (978-prefixed).

    Raises ValueError when the input is not a 10-character ISBN-10.
    """
    if len(isbn10) != 10:
        raise ValueError(f"not an ISBN-10 (length {len(isbn10)}): {isbn10!r}")
    body = "978" + isbn10[:9]
    # ISBN-13 check digit: weighted sum (1,3,1,3,...) over the 12 leading digits,
    # then (10 - sum mod 10) mod 10.
    weights = [1, 3] * 6
    total = sum(int(d) * w for d, w in zip(body, weights, strict=True))
    check = (10 - (total % 10)) % 10
    return body + str(check)


def dedupe_isbn_candidates(
    candidates: list[IdentifierCandidate],
) -> list[IdentifierCandidate]:
    """Collapse ISBN-10 / ISBN-13 same-edition pairs.

    For each non-ISBN candidate: pass through. For each ISBN candidate:
    canonicalize to ISBN-13. If two candidates resolve to the same ISBN-13,
    keep the one whose value is already in ISBN-13 form. On edition-hint
    conflict, prefer the non-UNSPECIFIED hint; if both are specified and
    differ, prefer the ISBN-13 form's hint.
    """
    by_key: dict[tuple[IdentifierKind, str], IdentifierCandidate] = {}
    for cand in candidates:
        if cand.kind != IdentifierKind.ISBN:
            key = (cand.kind, cand.value)
            if key not in by_key:
                by_key[key] = cand
            continue

        # ISBN: compute ISBN-13 key
        canon = cand.value
        try:
            key_val = canon if len(canon) == 13 else isbn10_to_isbn13(canon)
        except ValueError:
            # Malformed ISBN — keep as-is, don't merge.
            by_key[(cand.kind, canon)] = cand
            continue

        key = (cand.kind, key_val)
        existing = by_key.get(key)
        if existing is None:
            # Promote to ISBN-13 form if we're an ISBN-10
            if len(canon) == 10:
                by_key[key] = cand.model_copy(update={"value": key_val})
            else:
                by_key[key] = cand
            continue

        # Merge: ISBN-13 form wins on value; edition hint preference rules.
        winner_value = key_val  # always ISBN-13 in dedupe output
        # hint preference:
        existing_hint = existing.edition_hint
        new_hint = cand.edition_hint
        if existing_hint == EditionHint.UNSPECIFIED and new_hint != EditionHint.UNSPECIFIED:
            chosen_hint = new_hint
        elif new_hint == EditionHint.UNSPECIFIED and existing_hint != EditionHint.UNSPECIFIED:
            chosen_hint = existing_hint
        elif len(cand.value) == 13:
            chosen_hint = new_hint
        else:
            chosen_hint = existing_hint
        by_key[key] = IdentifierCandidate(
            kind=IdentifierKind.ISBN,
            value=winner_value,
            edition_hint=chosen_hint,
        )

    return list(by_key.values())
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_isbn.py -v
```

Expected: PASS (all 10 tests).

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/metadata.py tests/test_metadata_isbn.py
git commit -m "$(cat <<'EOF'
feat(metadata): ISBN canonicalize, isbn10->isbn13, dedupe helpers

Spec §5.2: canonicalize strips separators; isbn10_to_isbn13 recomputes
the check digit; dedupe_isbn_candidates collapses ISBN-10 / ISBN-13
same-edition pairs so MULTIPLE_ISBNS_DETECTED doesn't misfire on the
common case (e.g. The Holocaust Industry's two-form paperback).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Edition hint classification + priority picker

**Goal:** Two helpers for picking the right ISBN from a multi-edition print.

**Files:**
- Modify: `src/book_ingestion/metadata.py`
- Create: `tests/test_metadata_edition.py`

- [ ] **Step 1: Write failing tests**

`tests/test_metadata_edition.py`:

```python
"""Tests for edition-hint classification and priority picking."""
from __future__ import annotations

from book_ingestion.metadata import (
    EditionHint,
    IdentifierCandidate,
    IdentifierKind,
    classify_edition_hint,
    pick_identifier_value,
)


# --- classify_edition_hint ---------------------------------------------------

def test_classify_paperback() -> None:
    assert classify_edition_hint("paperback ISBN 9781844674879") == EditionHint.PAPERBACK


def test_classify_pbk_short() -> None:
    assert classify_edition_hint("(pbk) 9781844674879") == EditionHint.PAPERBACK


def test_classify_softcover() -> None:
    assert classify_edition_hint("Softcover edition 9781844674879") == EditionHint.PAPERBACK


def test_classify_trade_paperback() -> None:
    assert classify_edition_hint("Trade Paperback 9781844674879") == EditionHint.PAPERBACK


def test_classify_hardback() -> None:
    assert classify_edition_hint("Hardback ISBN 9781844674879") == EditionHint.HARDBACK


def test_classify_hardcover() -> None:
    assert classify_edition_hint("978-1-84467-487-9 hardcover") == EditionHint.HARDBACK


def test_classify_cloth() -> None:
    assert classify_edition_hint("9781844674879 cloth") == EditionHint.HARDBACK


def test_classify_ebook() -> None:
    assert classify_edition_hint("ebook ISBN 9781844674879") == EditionHint.EBOOK


def test_classify_kindle() -> None:
    assert classify_edition_hint("Kindle: 9781844674879") == EditionHint.EBOOK


def test_classify_epub() -> None:
    assert classify_edition_hint("9781844674879 (EPUB)") == EditionHint.EBOOK


def test_classify_pdf() -> None:
    assert classify_edition_hint("9781844674879 PDF edition") == EditionHint.EBOOK


def test_classify_no_match() -> None:
    assert classify_edition_hint("Some random text 9781844674879") == EditionHint.UNSPECIFIED


def test_classify_case_insensitive() -> None:
    assert classify_edition_hint("PAPERBACK") == EditionHint.PAPERBACK


# --- pick_identifier_value ---------------------------------------------------

def _isbn(value: str, hint: EditionHint = EditionHint.UNSPECIFIED) -> IdentifierCandidate:
    return IdentifierCandidate(kind=IdentifierKind.ISBN, value=value, edition_hint=hint)


def test_priority_paperback_wins() -> None:
    candidates = [
        _isbn("9781111111111", EditionHint.HARDBACK),
        _isbn("9782222222222", EditionHint.PAPERBACK),
        _isbn("9783333333333", EditionHint.UNSPECIFIED),
        _isbn("9784444444444", EditionHint.EBOOK),
    ]
    assert pick_identifier_value(candidates) == "9782222222222"


def test_priority_hardback_when_no_paperback() -> None:
    candidates = [
        _isbn("9781111111111", EditionHint.UNSPECIFIED),
        _isbn("9782222222222", EditionHint.HARDBACK),
        _isbn("9783333333333", EditionHint.EBOOK),
    ]
    assert pick_identifier_value(candidates) == "9782222222222"


def test_priority_unspecified_when_no_paperback_or_hardback() -> None:
    candidates = [
        _isbn("9781111111111", EditionHint.EBOOK),
        _isbn("9782222222222", EditionHint.UNSPECIFIED),
    ]
    assert pick_identifier_value(candidates) == "9782222222222"


def test_priority_ebook_last_resort() -> None:
    candidates = [_isbn("9781111111111", EditionHint.EBOOK)]
    assert pick_identifier_value(candidates) == "9781111111111"


def test_priority_empty_returns_none() -> None:
    assert pick_identifier_value([]) is None


def test_priority_first_in_tier_wins() -> None:
    candidates = [
        _isbn("9781111111111", EditionHint.PAPERBACK),
        _isbn("9782222222222", EditionHint.PAPERBACK),
    ]
    assert pick_identifier_value(candidates) == "9781111111111"
```

- [ ] **Step 2: Run, expect ImportError**

Expected: FAIL — `ImportError: cannot import name 'classify_edition_hint'`.

- [ ] **Step 3: Implement helpers**

Append to `src/book_ingestion/metadata.py`:

```python
_PAPERBACK_KEYWORDS = ("paperback", "pbk", "softcover", "trade paperback")
_HARDBACK_KEYWORDS = ("hardback", "hardcover", "cloth", " hb ")
_EBOOK_KEYWORDS = ("pdf", "ebook", "kindle", "epub", "digital")


def classify_edition_hint(text: str) -> EditionHint:
    """Classify an edition from surrounding text (case-insensitive).

    Used on a ~80-character window around each ISBN match. See spec §5.2.
    """
    lowered = text.lower()
    if any(kw in lowered for kw in _PAPERBACK_KEYWORDS):
        return EditionHint.PAPERBACK
    if any(kw in lowered for kw in _HARDBACK_KEYWORDS) or " hb " in f" {lowered} ":
        return EditionHint.HARDBACK
    if any(kw in lowered for kw in _EBOOK_KEYWORDS):
        return EditionHint.EBOOK
    return EditionHint.UNSPECIFIED


_EDITION_PRIORITY: tuple[EditionHint, ...] = (
    EditionHint.PAPERBACK,
    EditionHint.HARDBACK,
    EditionHint.UNSPECIFIED,
    EditionHint.EBOOK,
)


def pick_identifier_value(candidates: list[IdentifierCandidate]) -> str | None:
    """Choose the best candidate's value according to PAPERBACK > HARDBACK > UNSPECIFIED > EBOOK."""
    for tier in _EDITION_PRIORITY:
        for cand in candidates:
            if cand.edition_hint == tier:
                return cand.value
    return None
```

Note: the " hb " bookend test ensures we match the word `hb` as a standalone token, not as a substring of `kombucha`.

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_edition.py -v
```

Expected: PASS (19 tests).

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/metadata.py tests/test_metadata_edition.py
git commit -m "$(cat <<'EOF'
feat(metadata): edition hint classifier + priority picker

Spec §5.2: classify_edition_hint maps a text window to
PAPERBACK / HARDBACK / EBOOK / UNSPECIFIED; pick_identifier_value
picks per the spec's priority chain.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: PDF fixture helpers (reportlab)

**Goal:** Add reusable PDF-building helpers in `tests/fixtures/pdf.py` for synthetic-fixture tests. reportlab is already in dev extras.

**Files:**
- Create: `tests/fixtures/__init__.py`
- Create: `tests/fixtures/pdf.py`

This task has no implementation tests on its own — the fixtures are validated by the tests that use them in Tasks 8–12. Add one smoke test that builds each fixture and verifies the file exists and is non-empty.

- [ ] **Step 1: Write failing smoke test**

In a new file `tests/test_metadata_pdf.py` (will grow in later tasks):

```python
"""Tests for PdfMetadataExtractor + supporting PDF fixture helpers."""
from __future__ import annotations

from pathlib import Path

from tests.fixtures.pdf import (
    build_encrypted_pdf,
    build_pdf_with_all_caps_title,
    build_pdf_with_imprint,
    build_scanned_pdf,
)


def test_pdf_fixture_imprint_builds(tmp_path: Path) -> None:
    p = build_pdf_with_imprint(
        tmp_path / "imprint.pdf",
        title="Sample Book",
        subtitle="An Example",
        isbn_paperback="9781234567897",
        isbn_hardback="9781234567880",
        publisher="Example Press",
        places=["London", "New York"],
        year=2003,
        first_published_year=2000,
    )
    assert p.exists() and p.stat().st_size > 1000


def test_pdf_fixture_all_caps_builds(tmp_path: Path) -> None:
    p = build_pdf_with_all_caps_title(
        tmp_path / "caps.pdf",
        title_lines=["THE HOLOCAUST INDUSTRY"],
        subtitle="REFLECTIONS ON THE EXPLOITATION",
        author="Norman G. Finkelstein",
    )
    assert p.exists() and p.stat().st_size > 1000


def test_pdf_fixture_encrypted_builds(tmp_path: Path) -> None:
    p = build_encrypted_pdf(tmp_path / "enc.pdf", password="secret")
    assert p.exists() and p.stat().st_size > 0


def test_pdf_fixture_scanned_builds(tmp_path: Path) -> None:
    p = build_scanned_pdf(tmp_path / "scanned.pdf")
    assert p.exists() and p.stat().st_size > 0
```

- [ ] **Step 2: Run, expect ImportError**

```bash
uv run pytest tests/test_metadata_pdf.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'tests.fixtures'`.

- [ ] **Step 3: Implement fixture helpers**

`tests/fixtures/__init__.py`: empty file.

`tests/fixtures/pdf.py`:

```python
"""Synthetic PDF builders for tests. reportlab is in dev extras.

These helpers produce small, deterministic PDFs that exercise specific
extraction paths (imprint mining, ALL-CAPS title, encryption, no-text).
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


def build_pdf_with_imprint(
    path: Path,
    *,
    title: str,
    subtitle: str,
    isbn_paperback: str,
    isbn_hardback: str,
    publisher: str,
    places: list[str],
    year: int,
    first_published_year: int | None = None,
) -> Path:
    """Build a 3-page PDF: page 1 = title page, page 2 = copyright page, page 3 = body."""
    c = canvas.Canvas(str(path), pagesize=LETTER)
    # /Info entries
    c.setTitle(title)

    # Page 1: title page
    c.setFont("Helvetica-Bold", 24)
    c.drawString(72, 700, title)
    c.setFont("Helvetica", 16)
    c.drawString(72, 670, subtitle)
    c.showPage()

    # Page 2: copyright / imprint page
    c.setFont("Helvetica", 10)
    y = 720
    c.drawString(72, y, f"Published by {publisher}")
    y -= 14
    for place in places:
        c.drawString(72, y, place)
        y -= 14
    if first_published_year is not None:
        c.drawString(72, y, f"First published {first_published_year}")
        y -= 14
    c.drawString(72, y, f"Copyright © {year}")
    y -= 14
    c.drawString(72, y, f"Paperback ISBN {isbn_paperback}")
    y -= 14
    c.drawString(72, y, f"Hardback ISBN {isbn_hardback}")
    c.showPage()

    # Page 3: a body paragraph
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "This is the body of the book.")
    c.save()
    return path


def build_pdf_with_all_caps_title(
    path: Path,
    *,
    title_lines: list[str],
    subtitle: str | None,
    author: str,
) -> Path:
    """Build a 1-page PDF whose page 1 has an ALL-CAPS multi-line title.

    /Info /Title is intentionally left blank to force text-mining.
    """
    c = canvas.Canvas(str(path), pagesize=LETTER)
    # No setTitle() — leaves /Info /Title at the path stem
    y = 700
    c.setFont("Helvetica-Bold", 18)
    for line in title_lines:
        c.drawString(72, y, line)
        y -= 22
    y -= 8
    if subtitle is not None:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, y, subtitle)
        y -= 20
    y -= 12
    c.setFont("Helvetica", 12)
    c.drawString(72, y, author)
    c.save()
    return path


def build_encrypted_pdf(path: Path, *, password: str) -> Path:
    """Build a password-protected PDF."""
    c = canvas.Canvas(str(path), pagesize=LETTER, encrypt=password)
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "Encrypted content.")
    c.save()
    return path


def build_scanned_pdf(path: Path) -> Path:
    """Build a 'scanned' PDF: page exists, but no embedded text."""
    c = canvas.Canvas(str(path), pagesize=LETTER)
    # Page with only a thin line — no text.
    c.line(72, 720, 540, 720)
    c.showPage()
    c.save()
    return path
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_pdf.py -v
```

Expected: PASS (4 fixture smoke tests).

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

(mypy is scoped to `src/`, so it won't check `tests/` — that's fine.)

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/ tests/test_metadata_pdf.py
git commit -m "$(cat <<'EOF'
test(metadata): synthetic PDF fixture helpers (reportlab)

Four builders for the M2.0 PDF extractor: imprint+ISBNs, ALL-CAPS title,
encrypted, scanned (no-text). Used by tests in subsequent tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `PdfMetadataExtractor` — encryption + no-text paths

**Goal:** Skeleton extractor that handles the two early-return paths.

**Files:**
- Modify: `src/book_ingestion/extractors/base.py`
- Create: `src/book_ingestion/extractors/pdf.py`
- Modify: `tests/test_metadata_pdf.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_pdf.py`:

```python
from book_ingestion.extractors.pdf import PdfMetadataExtractor
from book_ingestion.metadata import BookMetadata, ErrorCode, WarningCode


def test_pdf_encrypted_returns_error(tmp_path: Path) -> None:
    p = build_encrypted_pdf(tmp_path / "enc.pdf", password="secret")
    m = PdfMetadataExtractor().extract_metadata(p)
    assert isinstance(m, BookMetadata)
    assert m.error == ErrorCode.ENCRYPTED
    assert m.title is None
    assert m.creators == []


def test_pdf_scanned_returns_no_text_warning(tmp_path: Path) -> None:
    p = build_scanned_pdf(tmp_path / "scanned.pdf")
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.error is None
    codes = {w.code for w in m.warnings}
    assert WarningCode.NO_TEXT_EXTRACTED in codes
```

- [ ] **Step 2: Run, expect ImportError**

```bash
uv run pytest tests/test_metadata_pdf.py -v -k "encrypted or scanned"
```

Expected: FAIL — `ImportError: cannot import name 'PdfMetadataExtractor'`.

- [ ] **Step 3: Define the Protocol**

Replace contents of `src/book_ingestion/extractors/base.py`:

```python
"""MetadataExtractor Protocol — see docs/superpowers/specs/2026-05-13-extract-metadata-design.md §2.

Each format gets one extractor. Backends remain separate (in `backends/`)
and are used for the heavyweight IR path; metadata extractors are
lightweight, no caching, no Docling.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from book_ingestion.metadata import BookMetadata


class MetadataExtractor(Protocol):
    """The interface every metadata extractor implements."""

    name: str

    def extract_metadata(self, path: Path, *, pages: int = 6) -> BookMetadata: ...
```

- [ ] **Step 4: Skeleton PDF extractor**

`src/book_ingestion/extractors/pdf.py`:

```python
"""PDF metadata extractor — pypdf-based.

Implements `MetadataExtractor` for PDFs. Reads `/Info` and the first N
pages of text. No Docling on this path.

See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §5.
"""
from __future__ import annotations

import logging
from pathlib import Path

from book_ingestion.metadata import (
    BookMetadata,
    ErrorCode,
    MetadataWarning,
    WarningCode,
)

logger = logging.getLogger(__name__)


class PdfMetadataExtractor:
    """PDF metadata extractor.

    `extract_metadata` always returns a BookMetadata; it does not raise on
    file-shape failures. See spec §7.
    """

    name = "pdf_pypdf"

    def extract_metadata(self, path: Path, *, pages: int = 6) -> BookMetadata:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(str(path))
        except (PdfReadError, OSError) as exc:
            logger.warning("pypdf failed to open %s: %s", path, exc)
            return BookMetadata(
                error=ErrorCode.MALFORMED_PDF,
                warnings=[MetadataWarning(
                    code=WarningCode.INCOMPLETE_EXTRACTION, detail=str(exc),
                )],
            )

        if reader.is_encrypted:
            return BookMetadata(error=ErrorCode.ENCRYPTED)

        # Pull text from up to `pages` leading pages.
        page_texts: list[str] = []
        for i, page in enumerate(reader.pages):
            if i >= pages:
                break
            try:
                page_texts.append(page.extract_text() or "")
            except Exception as exc:  # pypdf can raise on malformed streams
                logger.warning("pypdf failed to extract page %d of %s: %s", i, path, exc)
                page_texts.append("")

        joined = "\n".join(page_texts).strip()
        if not joined:
            return BookMetadata(warnings=[
                MetadataWarning(
                    code=WarningCode.NO_TEXT_EXTRACTED,
                    detail="PDF has no embedded text (scanned or empty)",
                ),
            ])

        # Subsequent tasks populate identifier, title, creators, etc.
        return BookMetadata()
```

- [ ] **Step 5: Run, expect pass**

```bash
uv run pytest tests/test_metadata_pdf.py -v -k "encrypted or scanned"
```

Expected: PASS.

- [ ] **Step 6: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 7: Commit**

```bash
git add src/book_ingestion/extractors/ tests/test_metadata_pdf.py
git commit -m "$(cat <<'EOF'
feat(metadata): PDF extractor skeleton — encryption + no-text paths

PdfMetadataExtractor with always-return contract (spec §7). Subsequent
tasks fill in identifier, title, creators, imprint mining.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: PDF — identifier extraction (DOI / arXiv / ISBN + dedupe)

**Goal:** Identifier regex pass over the extracted text + classification + dedupe.

**Files:**
- Modify: `src/book_ingestion/extractors/pdf.py`
- Modify: `tests/test_metadata_pdf.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_pdf.py`:

```python
from book_ingestion.metadata import EditionHint, IdentifierKind


def test_pdf_extracts_paperback_isbn(tmp_path: Path) -> None:
    p = build_pdf_with_imprint(
        tmp_path / "p.pdf",
        title="Sample",
        subtitle="A Subtitle",
        isbn_paperback="9781234567897",
        isbn_hardback="9781234567880",
        publisher="Example Press",
        places=["London"],
        year=2003,
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.identifier.kind == IdentifierKind.ISBN
    assert m.identifier.value == "9781234567897"  # paperback wins
    assert len(m.identifier.candidates) == 2
    assert {c.edition_hint for c in m.identifier.candidates} == {
        EditionHint.PAPERBACK, EditionHint.HARDBACK,
    }
    codes = {w.code for w in m.warnings}
    assert WarningCode.MULTIPLE_ISBNS_DETECTED in codes


def test_pdf_dedupes_isbn10_and_isbn13_no_warning(tmp_path: Path) -> None:
    """When a paperback prints both ISBN-10 and ISBN-13 forms, no MULTIPLE warning."""
    p = tmp_path / "dual.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "Title")
    c.showPage()
    c.drawString(72, 720, "Paperback ISBN 1-84467-487-8")
    c.drawString(72, 700, "Paperback ISBN 978-1-84467-487-9")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.identifier.value == "9781844674879"  # ISBN-13 form
    assert len(m.identifier.candidates) == 1
    codes = {w.code for w in m.warnings}
    assert WarningCode.MULTIPLE_ISBNS_DETECTED not in codes


def test_pdf_extracts_doi(tmp_path: Path) -> None:
    p = tmp_path / "doi.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "DOI: 10.1234/abcde.fghij")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.identifier.kind == IdentifierKind.DOI
    assert m.identifier.value == "10.1234/abcde.fghij"


def test_pdf_extracts_arxiv(tmp_path: Path) -> None:
    p = tmp_path / "arxiv.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "arXiv: 2301.12345")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.identifier.kind == IdentifierKind.ARXIV
    assert m.identifier.value == "2301.12345"
```

Add to imports at top:
```python
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/test_metadata_pdf.py -v -k "isbn or doi or arxiv"
```

Expected: FAIL — assertions fail because the extractor currently returns `BookMetadata()`.

- [ ] **Step 3: Implement identifier extraction**

Add to `src/book_ingestion/extractors/pdf.py` (replace the trailing `return BookMetadata()` block):

```python
import re

from book_ingestion.metadata import (
    Identifier,
    IdentifierCandidate,
    IdentifierKind,
    canonicalize_isbn,
    classify_edition_hint,
    dedupe_isbn_candidates,
    pick_identifier_value,
)

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"(?:arXiv:\s*|arxiv\.org/abs/)(\d{4}\.\d{4,5})", re.IGNORECASE)
_ISBN13_RE = re.compile(r"(?:ISBN[ -]*)?(97[89][- 0-9]{10,})", re.IGNORECASE)
_ISBN10_RE = re.compile(r"(?:ISBN[ -]*)?([0-9][- 0-9]{8,10}[0-9X])", re.IGNORECASE)


def _extract_identifier(text: str, warnings: list[MetadataWarning]) -> Identifier:
    # DOI — first match
    doi_m = _DOI_RE.search(text)
    if doi_m:
        value = doi_m.group(0)
        return Identifier(
            kind=IdentifierKind.DOI,
            value=value,
            candidates=[IdentifierCandidate(kind=IdentifierKind.DOI, value=value)],
        )

    # arXiv — first match
    arxiv_m = _ARXIV_RE.search(text)
    if arxiv_m:
        value = arxiv_m.group(1)
        return Identifier(
            kind=IdentifierKind.ARXIV,
            value=value,
            candidates=[IdentifierCandidate(kind=IdentifierKind.ARXIV, value=value)],
        )

    # ISBNs — gather all matches, classify by window, then dedupe.
    raw_candidates: list[IdentifierCandidate] = []
    for m in _ISBN13_RE.finditer(text):
        raw = m.group(1)
        canon = canonicalize_isbn(raw)
        if len(canon) != 13 or not canon.startswith(("978", "979")):
            continue
        window = text[max(0, m.start() - 80) : m.end() + 80]
        raw_candidates.append(IdentifierCandidate(
            kind=IdentifierKind.ISBN, value=canon,
            edition_hint=classify_edition_hint(window),
        ))
    for m in _ISBN10_RE.finditer(text):
        raw = m.group(1)
        canon = canonicalize_isbn(raw)
        if len(canon) != 10:
            continue
        # Avoid double-matching the prefix of an ISBN-13
        if any(canon == c.value[3:] for c in raw_candidates if len(c.value) == 13):
            continue
        window = text[max(0, m.start() - 80) : m.end() + 80]
        raw_candidates.append(IdentifierCandidate(
            kind=IdentifierKind.ISBN, value=canon,
            edition_hint=classify_edition_hint(window),
        ))

    if not raw_candidates:
        return Identifier()

    deduped = dedupe_isbn_candidates(raw_candidates)
    if len(deduped) > 1:
        warnings.append(MetadataWarning(
            code=WarningCode.MULTIPLE_ISBNS_DETECTED,
            detail=f"{len(deduped)} distinct ISBN editions detected",
        ))

    value = pick_identifier_value(deduped)
    return Identifier(
        kind=IdentifierKind.ISBN if value else None,
        value=value,
        candidates=deduped,
    )
```

Replace the trailing block in `extract_metadata`:

```python
        # Replace `return BookMetadata()` with:
        warnings: list[MetadataWarning] = []
        identifier = _extract_identifier(joined, warnings)

        return BookMetadata(
            identifier=identifier,
            warnings=warnings,
        )
```

- [ ] **Step 4: Run identifier tests**

```bash
uv run pytest tests/test_metadata_pdf.py -v -k "isbn or doi or arxiv"
```

Expected: PASS.

- [ ] **Step 5: Run all PDF tests so far**

```bash
uv run pytest tests/test_metadata_pdf.py -v
```

Expected: all green.

- [ ] **Step 6: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 7: Commit**

```bash
git add src/book_ingestion/extractors/pdf.py tests/test_metadata_pdf.py
git commit -m "$(cat <<'EOF'
feat(metadata): PDF identifier extraction (DOI / arXiv / ISBN + dedupe)

ISBN path: regex pass, canonicalize, classify by 80-char window, dedupe
ISBN-10/13 same-edition pairs, pick by PAPERBACK > HARDBACK >
UNSPECIFIED > EBOOK. MULTIPLE_ISBNS_DETECTED fires only on the deduped
set.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: PDF — title / subtitle

**Goal:** Extract title and subtitle per spec §5.3 (Info → ALL-CAPS → first-line fallback).

**Files:**
- Modify: `src/book_ingestion/extractors/pdf.py`
- Modify: `tests/test_metadata_pdf.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_pdf.py`:

```python
def test_pdf_uses_info_title_when_present(tmp_path: Path) -> None:
    p = build_pdf_with_imprint(
        tmp_path / "info.pdf",
        title="The Real Title",
        subtitle="Subtitle Here",
        isbn_paperback="9781234567897",
        isbn_hardback="9781234567880",
        publisher="X",
        places=["L"],
        year=2000,
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.title == "The Real Title"


def test_pdf_falls_back_to_all_caps_when_info_blank(tmp_path: Path) -> None:
    p = build_pdf_with_all_caps_title(
        tmp_path / "caps.pdf",
        title_lines=["THE HOLOCAUST INDUSTRY"],
        subtitle="REFLECTIONS ON THE EXPLOITATION",
        author="Norman G. Finkelstein",
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.title == "THE HOLOCAUST INDUSTRY"
    assert m.subtitle == "REFLECTIONS ON THE EXPLOITATION"
    assert m.full_title == "THE HOLOCAUST INDUSTRY: REFLECTIONS ON THE EXPLOITATION"
    codes = {w.code for w in m.warnings}
    assert WarningCode.TITLE_ALL_CAPS_IN_SOURCE in codes


def test_pdf_joins_multi_line_all_caps(tmp_path: Path) -> None:
    p = build_pdf_with_all_caps_title(
        tmp_path / "multi.pdf",
        title_lines=["THE HOLOCAUST", "INDUSTRY"],
        subtitle=None,
        author="Author",
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.title == "THE HOLOCAUST INDUSTRY"
    assert m.subtitle is None
    assert m.full_title == "THE HOLOCAUST INDUSTRY"


def test_pdf_info_title_equal_to_stem_is_ignored(tmp_path: Path) -> None:
    """When /Info /Title is just the filename, fall through to text mining."""
    p = tmp_path / "MyFile.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setTitle("MyFile")  # equal to path.stem
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "REAL TITLE")
    c.save()
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.title == "REAL TITLE"
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/test_metadata_pdf.py -v -k "title"
```

Expected: FAIL — title not populated.

- [ ] **Step 3: Implement title extraction**

Add to `src/book_ingestion/extractors/pdf.py`:

```python
def _info_title(reader: "PdfReader", path: Path) -> str | None:  # type: ignore[name-defined]
    """Return /Info /Title if present, non-empty, and not equal to path.stem."""
    info = reader.metadata
    if info is None:
        return None
    raw = info.get("/Title")
    if not raw:
        return None
    text = str(raw).strip()
    if not text or text == path.stem:
        return None
    return text


def _is_all_caps(line: str) -> bool:
    has_letter = any(c.isalpha() for c in line)
    return has_letter and line.upper() == line


def _mine_title_from_page_one(text_page_one: str) -> tuple[str | None, str | None]:
    """Return (title, subtitle) from page-1 text mining.

    Strategy (spec §5.3):
      - Find first ALL-CAPS block (consecutive ALL-CAPS lines without trailing punct).
        Join with single spaces. Subtitle = next ALL-CAPS block before author signal.
      - Else, first non-trivial line (≥5 chars, not a page number).
        Subtitle = next non-empty line if shorter than title.
    """
    lines = [line.strip() for line in text_page_one.splitlines() if line.strip()]
    if not lines:
        return None, None

    # ALL-CAPS path
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.lower().startswith("by "):
            break
        if _is_all_caps(line):
            current.append(line)
        else:
            if current:
                blocks.append(current)
                current = []
            # Continue scanning — later ALL-CAPS may be subtitle.
    if current:
        blocks.append(current)

    if blocks:
        title = " ".join(blocks[0])
        subtitle = " ".join(blocks[1]) if len(blocks) > 1 else None
        return title, subtitle

    # First non-trivial line fallback
    for line in lines:
        if len(line) < 5:
            continue
        if line.isdigit():
            continue
        title = line
        # Subtitle: next non-empty line shorter than title
        idx = lines.index(line)
        rest = lines[idx + 1 :]
        for r in rest:
            if r.lower().startswith("by "):
                break
            if 0 < len(r) < len(title):
                return title, r
        return title, None
    return None, None


def _compose_full_title(title: str | None, subtitle: str | None) -> str | None:
    if title is None:
        return None
    if subtitle is None:
        return title
    return f"{title}: {subtitle}"
```

Update `extract_metadata` body to compute title fields:

```python
        warnings: list[MetadataWarning] = []
        identifier = _extract_identifier(joined, warnings)

        info_title = _info_title(reader, path)
        if info_title is not None:
            title: str | None = info_title
            subtitle: str | None = None  # /Info has no subtitle field
        else:
            title, subtitle = _mine_title_from_page_one(page_texts[0] if page_texts else "")

        if title is not None and _is_all_caps(title):
            warnings.append(MetadataWarning(code=WarningCode.TITLE_ALL_CAPS_IN_SOURCE))

        full_title = _compose_full_title(title, subtitle)

        return BookMetadata(
            identifier=identifier,
            title=title,
            subtitle=subtitle,
            full_title=full_title,
            warnings=warnings,
        )
```

- [ ] **Step 4: Run title tests**

```bash
uv run pytest tests/test_metadata_pdf.py -v -k "title"
```

Expected: PASS.

- [ ] **Step 5: Run all PDF tests**

```bash
uv run pytest tests/test_metadata_pdf.py -v
```

Expected: all green.

- [ ] **Step 6: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 7: Commit**

```bash
git add src/book_ingestion/extractors/pdf.py tests/test_metadata_pdf.py
git commit -m "$(cat <<'EOF'
feat(metadata): PDF title/subtitle extraction

Two-stage per spec §5.3: /Info /Title primary (when non-empty and not
equal to path.stem), page-1 text mining fallback (ALL-CAPS block, else
first non-trivial line). Composes full_title; flags
TITLE_ALL_CAPS_IN_SOURCE without auto title-casing.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: PDF — creators

**Goal:** Extract creators from the page-1 text block following the title.

**Files:**
- Modify: `src/book_ingestion/extractors/pdf.py`
- Modify: `tests/test_metadata_pdf.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_pdf.py`:

```python
from book_ingestion.metadata import Creator, CreatorRole


def test_pdf_extracts_single_author_by_form(tmp_path: Path) -> None:
    p = tmp_path / "single.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.setFont("Helvetica", 12)
    c.drawString(72, 650, "by Norman G. Finkelstein")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert len(m.creators) == 1
    assert m.creators[0].role == CreatorRole.AUTHOR
    assert m.creators[0].first_name == "Norman G."
    assert m.creators[0].last_name == "Finkelstein"


def test_pdf_extracts_comma_form_author(tmp_path: Path) -> None:
    p = tmp_path / "comma.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.setFont("Helvetica", 12)
    c.drawString(72, 650, "Finkelstein, Norman G.")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert len(m.creators) == 1
    assert m.creators[0].first_name == "Norman G."
    assert m.creators[0].last_name == "Finkelstein"


def test_pdf_preserves_creator_order(tmp_path: Path) -> None:
    p = tmp_path / "two.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.setFont("Helvetica", 12)
    c.drawString(72, 650, "by Jane Smith and John Jones")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert [c.last_name for c in m.creators] == ["Smith", "Jones"]


def test_pdf_detects_translator_role(tmp_path: Path) -> None:
    p = tmp_path / "trans.pdf"
    c = canvas.Canvas(str(p), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 700, "TITLE")
    c.setFont("Helvetica", 12)
    c.drawString(72, 650, "translated by Jane Smith")
    c.save()

    m = PdfMetadataExtractor().extract_metadata(p)
    assert len(m.creators) == 1
    assert m.creators[0].role == CreatorRole.TRANSLATOR
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/test_metadata_pdf.py -v -k "creator or author"
```

Expected: FAIL — `m.creators == []`.

- [ ] **Step 3: Implement creator extraction**

Add to `src/book_ingestion/extractors/pdf.py`:

```python
from book_ingestion.metadata import Creator, CreatorRole

_ROLE_PREFIXES: dict[str, CreatorRole] = {
    "translated by ": CreatorRole.TRANSLATOR,
    "edited by ": CreatorRole.EDITOR,
    "with foreword by ": CreatorRole.FOREWORD,
    "with a foreword by ": CreatorRole.FOREWORD,
    "illustrated by ": CreatorRole.ILLUSTRATOR,
}


def _parse_one_name(raw: str) -> Creator:
    """Parse a single creator name string into a Creator (role=AUTHOR; caller may override)."""
    stripped = raw.strip().rstrip(",;")
    if "," in stripped:
        # "Last, First [Middle]"
        last, _, first = stripped.partition(",")
        last_name = last.strip() or None
        first_name = first.strip() or None
    else:
        parts = stripped.rsplit(None, 1)
        if len(parts) == 2:
            first_name, last_name = parts[0].strip() or None, parts[1].strip() or None
        else:
            first_name, last_name = None, stripped or None
    return Creator(first_name=first_name, last_name=last_name, raw=raw)


def _split_creator_string(text: str) -> list[str]:
    """Split a creator string on ' and ' first, then on commas (when likely two people)."""
    # First split on ' and '
    parts = [p.strip() for p in re.split(r"\s+and\s+", text) if p.strip()]
    # If only one part remains, try comma split as a fallback for "X, Y, Z" lists.
    # (Don't split on commas if the part contains a comma-form name with no 'and' —
    # that produces a single Creator; comma-list authors typically use 'and' too.)
    return parts


def _extract_creators(text_page_one: str) -> list[Creator]:
    """Find a creator line on page 1 and parse it into Creator objects."""
    lines = [line.strip() for line in text_page_one.splitlines() if line.strip()]
    for raw in lines:
        lowered = raw.lower()
        matched_role: CreatorRole | None = None
        remainder = raw
        for prefix, role in _ROLE_PREFIXES.items():
            if lowered.startswith(prefix):
                matched_role = role
                remainder = raw[len(prefix):]
                break
        if matched_role is None and lowered.startswith("by "):
            remainder = raw[3:]
            matched_role = CreatorRole.AUTHOR
        if matched_role is None:
            continue

        parts = _split_creator_string(remainder)
        creators: list[Creator] = []
        for part in parts:
            c = _parse_one_name(part)
            creators.append(c.model_copy(update={"role": matched_role}))
        if creators:
            return creators

    # No explicit role prefix — try comma-form "Last, First" on a standalone line.
    for raw in lines:
        if re.match(r"^[A-Z][A-Za-z\-]+,\s*[A-Z]", raw):
            return [_parse_one_name(raw)]

    return []
```

Update `extract_metadata` body:

```python
        creators = _extract_creators(page_texts[0] if page_texts else "")
        ...
        return BookMetadata(
            identifier=identifier,
            title=title,
            subtitle=subtitle,
            full_title=full_title,
            creators=creators,
            warnings=warnings,
        )
```

- [ ] **Step 4: Run creator tests**

```bash
uv run pytest tests/test_metadata_pdf.py -v -k "creator or author or translator"
```

Expected: PASS.

- [ ] **Step 5: Run all PDF tests**

```bash
uv run pytest tests/test_metadata_pdf.py -v
```

- [ ] **Step 6: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 7: Commit**

```bash
git add src/book_ingestion/extractors/pdf.py tests/test_metadata_pdf.py
git commit -m "$(cat <<'EOF'
feat(metadata): PDF creator extraction (single, multi, roles, order)

Spec §5.4: 'by X', 'translated by X', 'edited by X', 'X, Y' splits;
'Last, First' comma-form name parsing. Source order preserved.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: PDF — publisher / places / date / edition

**Goal:** Imprint-block mining for publisher, places, dates, edition string.

**Files:**
- Modify: `src/book_ingestion/extractors/pdf.py`
- Modify: `tests/test_metadata_pdf.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_pdf.py`:

```python
def test_pdf_extracts_publisher_places_date(tmp_path: Path) -> None:
    p = build_pdf_with_imprint(
        tmp_path / "imp.pdf",
        title="Sample",
        subtitle="Sub",
        isbn_paperback="9781234567897",
        isbn_hardback="9781234567880",
        publisher="Example Press",
        places=["London", "New York"],
        year=2003,
        first_published_year=2000,
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.publisher == "Example Press"
    assert m.places == ["London", "New York"]
    assert m.date == "2003"
    assert m.first_published == "2000"
    codes = {w.code for w in m.warnings}
    assert WarningCode.MULTIPLE_PLACES_DETECTED in codes


def test_pdf_single_year_first_published_none(tmp_path: Path) -> None:
    p = build_pdf_with_imprint(
        tmp_path / "one.pdf",
        title="Sample",
        subtitle="Sub",
        isbn_paperback="9781234567897",
        isbn_hardback="9781234567880",
        publisher="Example Press",
        places=["London"],
        year=2003,
        first_published_year=None,
    )
    m = PdfMetadataExtractor().extract_metadata(p)
    assert m.date == "2003"
    assert m.first_published is None
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/test_metadata_pdf.py -v -k "publisher or places or date"
```

Expected: FAIL.

- [ ] **Step 3: Implement imprint extraction**

Add to `src/book_ingestion/extractors/pdf.py`:

```python
_PUBLISHER_KEYWORDS = ("Press", "Books", "Publishing", "Verso", "Penguin", "Routledge")
_KNOWN_PLACES = (
    "London", "New York", "Cambridge", "Oxford", "Boston", "Chicago",
    "Edinburgh", "Glasgow", "Manchester", "Paris", "Berlin", "Rome",
    "Washington", "Toronto", "Sydney", "Melbourne", "Dublin", "Tokyo",
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_EDITION_RE = re.compile(
    r"((?:First|Second|Third|Fourth|Fifth|Revised|Updated|Paperback|Hardback)"
    r"(?:\s+\w+)*?\s+Edition)",
    re.IGNORECASE,
)


def _extract_publisher(imprint_text: str) -> str | None:
    for line in imprint_text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned.lower().startswith("published by "):
            return cleaned[len("Published by "):].strip()
        if any(kw in cleaned for kw in _PUBLISHER_KEYWORDS):
            # Strip a leading "Published by " or similar
            return cleaned.split("by ", 1)[-1] if cleaned.lower().startswith("published") else cleaned
    return None


def _extract_places(imprint_text: str) -> list[str]:
    places: list[str] = []
    for line in imprint_text.splitlines():
        for known in _KNOWN_PLACES:
            if known in line and known not in places:
                places.append(known)
    return places


def _extract_dates(imprint_text: str) -> tuple[str | None, str | None]:
    """Return (date, first_published).

    Strategy: scan all 4-digit years; take min as first_published if it's the
    earliest © year and there's a distinct later year as `date`. If only one
    year, that's `date`.
    """
    years = sorted({m.group(0) for m in _YEAR_RE.finditer(imprint_text)})
    if not years:
        return None, None
    if len(years) == 1:
        return years[0], None
    return years[-1], years[0]  # most recent → date; earliest → first_published


def _extract_edition(imprint_text: str) -> str | None:
    m = _EDITION_RE.search(imprint_text)
    return m.group(1) if m else None
```

Update `extract_metadata` to compute these from the joined text of pages 2..N:

```python
        # Imprint block: pages 2..N (page index 1.. in 0-based; pypdf is 0-based)
        imprint_text = "\n".join(page_texts[1:]) if len(page_texts) > 1 else ""
        publisher = _extract_publisher(imprint_text)
        places = _extract_places(imprint_text)
        if len(places) > 1:
            warnings.append(MetadataWarning(code=WarningCode.MULTIPLE_PLACES_DETECTED))
        date, first_published = _extract_dates(imprint_text)
        edition = _extract_edition(imprint_text)

        return BookMetadata(
            identifier=identifier,
            title=title,
            subtitle=subtitle,
            full_title=full_title,
            creators=creators,
            publisher=publisher,
            places=places,
            date=date,
            first_published=first_published,
            edition=edition,
            language="en",  # PDF default per spec §5.6
            warnings=warnings,
        )
```

- [ ] **Step 4: Run imprint tests**

```bash
uv run pytest tests/test_metadata_pdf.py -v -k "publisher or places or date"
```

Expected: PASS.

- [ ] **Step 5: Run full PDF test suite**

```bash
uv run pytest tests/test_metadata_pdf.py -v
```

- [ ] **Step 6: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 7: Commit**

```bash
git add src/book_ingestion/extractors/pdf.py tests/test_metadata_pdf.py
git commit -m "$(cat <<'EOF'
feat(metadata): PDF publisher / places / date / edition extraction

Spec §5.5: imprint-block mining on pages 2..N. Publisher via keyword
or 'Published by'; places via known-city list (flagging
MULTIPLE_PLACES_DETECTED); dates by min/max copyright year; edition
via phrase regex. Language defaults to 'en' (spec §5.6).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: EPUB fixture helpers (stdlib)

**Goal:** Add stdlib-based EPUB builders for synthetic-fixture tests.

**Files:**
- Create: `tests/fixtures/epub.py`
- Create: `tests/test_metadata_epub.py`

- [ ] **Step 1: Write failing fixture smoke tests**

`tests/test_metadata_epub.py`:

```python
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
```

- [ ] **Step 2: Run, expect ImportError**

```bash
uv run pytest tests/test_metadata_epub.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement EPUB fixture helpers**

`tests/fixtures/epub.py`:

```python
"""Synthetic EPUB builders for tests. stdlib only (zipfile + xml strings).

Each builder produces a minimal-but-valid EPUB exercising a specific path:
- build_epub: well-formed EPUB2 with given metadata.
- build_epub_with_truncated_title: dc:title is bare; full title on title-page xhtml.
- build_epub_with_drm: META-INF/encryption.xml present with Adobe DRM namespace.
- build_malformed_epub: missing OPF (no container.xml entry).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

_CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="{opf_path}" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_OPF_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    {metadata_inner}
  </metadata>
  <manifest>
    {manifest_inner}
  </manifest>
  <spine toc="ncx">
    {spine_inner}
  </spine>
  {guide_block}
</package>
"""

_TITLE_PAGE_XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>{title}</title></head>
  <body><h1>{title}</h1></body>
</html>
"""

_DRM_ENCRYPTION_XML = """<?xml version="1.0"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <EncryptedData xmlns="http://www.w3.org/2001/04/xmlenc#"
                 xmlns:adept="http://ns.adobe.com/adept">
    <EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>
  </EncryptedData>
</encryption>
"""


def build_epub(
    path: Path,
    *,
    dc_title: str,
    creators: list[tuple[str, str]],   # (text, opf:role)
    isbn: str | None,
    publisher: str | None,
    language: str,
    eisbn: str | None = None,
    date: str | None = None,
) -> Path:
    """Build a minimal EPUB2 with the supplied metadata."""
    metadata_lines: list[str] = [f'<dc:title>{dc_title}</dc:title>']
    for text, role in creators:
        metadata_lines.append(f'<dc:creator opf:role="{role}">{text}</dc:creator>')
    if publisher:
        metadata_lines.append(f'<dc:publisher>{publisher}</dc:publisher>')
    metadata_lines.append(f'<dc:language>{language}</dc:language>')
    if isbn:
        metadata_lines.append(f'<dc:identifier id="bookid" opf:scheme="ISBN">{isbn}</dc:identifier>')
        metadata_lines.append(f'<meta name="isbn" content="{isbn}"/>')
    if eisbn:
        metadata_lines.append(f'<meta name="eisbn" content="{eisbn}"/>')
    if date:
        metadata_lines.append(f'<dc:date opf:event="publication">{date}</dc:date>')

    opf = _OPF_TEMPLATE.format(
        metadata_inner="\n    ".join(metadata_lines),
        manifest_inner='<item id="t" href="title.xhtml" media-type="application/xhtml+xml"/>',
        spine_inner='<itemref idref="t"/>',
        guide_block="",
    )
    title_page = _TITLE_PAGE_XHTML.format(title=dc_title)

    _write_zip(
        path,
        {
            "mimetype": "application/epub+zip",
            "META-INF/container.xml": _CONTAINER_XML.format(opf_path="OEBPS/content.opf"),
            "OEBPS/content.opf": opf,
            "OEBPS/title.xhtml": title_page,
        },
    )
    return path


def build_epub_with_truncated_title(
    path: Path,
    *,
    dc_title: str,
    full_title_in_xhtml: str,
) -> Path:
    """Build an EPUB whose <dc:title> is bare; the title page xhtml has the full title."""
    metadata_lines = [
        f'<dc:title>{dc_title}</dc:title>',
        '<dc:language>en</dc:language>',
    ]
    opf = _OPF_TEMPLATE.format(
        metadata_inner="\n    ".join(metadata_lines),
        manifest_inner='<item id="t" href="title.xhtml" media-type="application/xhtml+xml"/>',
        spine_inner='<itemref idref="t"/>',
        guide_block='<guide><reference type="title-page" href="title.xhtml" title="Title"/></guide>',
    )
    title_page = _TITLE_PAGE_XHTML.format(title=full_title_in_xhtml)
    _write_zip(
        path,
        {
            "mimetype": "application/epub+zip",
            "META-INF/container.xml": _CONTAINER_XML.format(opf_path="OEBPS/content.opf"),
            "OEBPS/content.opf": opf,
            "OEBPS/title.xhtml": title_page,
        },
    )
    return path


def build_epub_with_drm(path: Path) -> Path:
    """Build an EPUB with Adobe DRM markers in META-INF/encryption.xml."""
    _write_zip(
        path,
        {
            "mimetype": "application/epub+zip",
            "META-INF/container.xml": _CONTAINER_XML.format(opf_path="OEBPS/content.opf"),
            "META-INF/encryption.xml": _DRM_ENCRYPTION_XML,
            "OEBPS/content.opf": "<package/>",
        },
    )
    return path


def build_malformed_epub(path: Path) -> Path:
    """Build a ZIP that looks like an EPUB but has no container.xml."""
    _write_zip(path, {"mimetype": "application/epub+zip"})
    return path


def _write_zip(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype must be uncompressed and first per the EPUB spec
        if "mimetype" in files:
            zf.writestr(zipfile.ZipInfo("mimetype"), files["mimetype"], compress_type=zipfile.ZIP_STORED)
        for name, content in files.items():
            if name == "mimetype":
                continue
            zf.writestr(name, content)
```

- [ ] **Step 4: Run fixture smoke tests**

```bash
uv run pytest tests/test_metadata_epub.py -v
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/epub.py tests/test_metadata_epub.py
git commit -m "$(cat <<'EOF'
test(metadata): synthetic EPUB fixture helpers (stdlib)

Four builders: well-formed EPUB2, truncated dc:title with full title
in xhtml, Adobe-DRM, missing-OPF malformed. Used by tests in
subsequent tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: `EpubMetadataExtractor` — DRM + malformed paths

**Goal:** Skeleton extractor with the two hard-failure paths.

**Files:**
- Create: `src/book_ingestion/extractors/epub.py`
- Modify: `tests/test_metadata_epub.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_epub.py`:

```python
from book_ingestion.extractors.epub import EpubMetadataExtractor
from book_ingestion.metadata import BookMetadata, ErrorCode


def test_epub_drm_returns_error(tmp_path: Path) -> None:
    p = build_epub_with_drm(tmp_path / "drm.epub")
    m = EpubMetadataExtractor().extract_metadata(p)
    assert isinstance(m, BookMetadata)
    assert m.error == ErrorCode.DRM_PROTECTED
    assert m.title is None


def test_epub_malformed_no_container_returns_error(tmp_path: Path) -> None:
    p = build_malformed_epub(tmp_path / "bad.epub")
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.error == ErrorCode.MALFORMED_EPUB


def test_epub_not_a_zip_returns_error(tmp_path: Path) -> None:
    p = tmp_path / "notzip.epub"
    p.write_bytes(b"this is not a zip file")
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.error == ErrorCode.MALFORMED_EPUB
```

- [ ] **Step 2: Run, expect ImportError**

```bash
uv run pytest tests/test_metadata_epub.py -v -k "drm or malformed or notzip"
```

Expected: FAIL — `ImportError: cannot import name 'EpubMetadataExtractor'`.

- [ ] **Step 3: Implement skeleton**

`src/book_ingestion/extractors/epub.py`:

```python
"""EPUB metadata extractor — stdlib zipfile + xml.etree.

Implements `MetadataExtractor` for EPUBs. Reads `META-INF/container.xml`
to locate the OPF, then parses Dublin Core metadata. No external XML
library (no lxml).

See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §6.
"""
from __future__ import annotations

import logging
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from book_ingestion.metadata import (
    BookMetadata,
    ErrorCode,
    MetadataWarning,
    WarningCode,
)

logger = logging.getLogger(__name__)

_ADOBE_DRM_NS = "http://ns.adobe.com/adept"
_APPLE_DRM_NS = "com.apple.iBooks"


class EpubMetadataExtractor:
    """EPUB metadata extractor.

    `extract_metadata` always returns a BookMetadata; it does not raise on
    file-shape failures. See spec §7.
    """

    name = "epub_stdlib"

    def extract_metadata(self, path: Path, *, pages: int = 6) -> BookMetadata:
        # `pages` is ignored for EPUB (no concept of leading pages).
        del pages
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as exc:
            logger.warning("EPUB %s is not a valid zip: %s", path, exc)
            return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

        try:
            with zf:
                names = set(zf.namelist())

                # DRM detection
                if "META-INF/encryption.xml" in names:
                    try:
                        enc_bytes = zf.read("META-INF/encryption.xml")
                        if _ADOBE_DRM_NS.encode() in enc_bytes or _APPLE_DRM_NS.encode() in enc_bytes:
                            return BookMetadata(error=ErrorCode.DRM_PROTECTED)
                    except KeyError:
                        pass

                # Missing container.xml is malformed
                if "META-INF/container.xml" not in names:
                    return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

                # Subsequent tasks parse the OPF.
                return BookMetadata()
        except zipfile.BadZipFile as exc:
            logger.warning("EPUB %s zip read failed: %s", path, exc)
            return BookMetadata(
                error=ErrorCode.MALFORMED_EPUB,
                warnings=[MetadataWarning(
                    code=WarningCode.INCOMPLETE_EXTRACTION, detail=str(exc),
                )],
            )
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_epub.py -v -k "drm or malformed or notzip"
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/extractors/epub.py tests/test_metadata_epub.py
git commit -m "$(cat <<'EOF'
feat(metadata): EPUB extractor skeleton — DRM + malformed paths

EpubMetadataExtractor with always-return contract. DRM detected via
encryption.xml namespace; missing container.xml or non-zip → malformed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: EPUB — OPF basics (title, publisher, language)

**Goal:** Parse the OPF and pull simple Dublin Core fields.

**Files:**
- Modify: `src/book_ingestion/extractors/epub.py`
- Modify: `tests/test_metadata_epub.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_epub.py`:

```python
from book_ingestion.metadata import WarningCode


def test_epub_extracts_dc_title(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "t.epub",
        dc_title="Sample Book",
        creators=[("Smith, Jane", "aut")],
        isbn=None,
        publisher=None,
        language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.title == "Sample Book"
    assert m.full_title == "Sample Book"


def test_epub_extracts_publisher(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "pub.epub",
        dc_title="X",
        creators=[],
        isbn=None,
        publisher="Example Press",
        language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.publisher == "Example Press"


def test_epub_normalises_language_and_flags(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "lang.epub",
        dc_title="X",
        creators=[],
        isbn=None,
        publisher=None,
        language="en-US",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.language == "en"
    codes = {w.code for w in m.warnings}
    assert WarningCode.LANGUAGE_NORMALISED in codes


def test_epub_language_no_normalisation_no_flag(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "lang2.epub",
        dc_title="X",
        creators=[],
        isbn=None,
        publisher=None,
        language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.language == "en"
    codes = {w.code for w in m.warnings}
    assert WarningCode.LANGUAGE_NORMALISED not in codes
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/test_metadata_epub.py -v -k "title or publisher or language"
```

Expected: FAIL.

- [ ] **Step 3: Implement OPF parsing**

Update `src/book_ingestion/extractors/epub.py`:

```python
_DC_NS = "http://purl.org/dc/elements/1.1/"
_OPF_NS = "http://www.idpf.org/2007/opf"
_CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"


def _find_opf_path(container_xml: bytes) -> str | None:
    try:
        root = ET.fromstring(container_xml)
    except ET.ParseError:
        return None
    rootfile = root.find(f".//{{{_CONTAINER_NS}}}rootfile")
    if rootfile is None:
        return None
    return rootfile.get("full-path")


def _normalise_language(raw: str) -> tuple[str, bool]:
    """Normalise a BCP-47 tag to its primary subtag. Returns (out, changed)."""
    primary = raw.split("-", 1)[0].lower()
    return primary, primary != raw
```

Replace the trailing `return BookMetadata()` in `extract_metadata` with full OPF parsing:

```python
                container_xml = zf.read("META-INF/container.xml")
                opf_path = _find_opf_path(container_xml)
                if opf_path is None or opf_path not in names:
                    return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

                try:
                    opf_root = ET.fromstring(zf.read(opf_path))
                except ET.ParseError as exc:
                    logger.warning("EPUB OPF parse failed for %s: %s", path, exc)
                    return BookMetadata(
                        error=ErrorCode.MALFORMED_EPUB,
                        warnings=[MetadataWarning(
                            code=WarningCode.INCOMPLETE_EXTRACTION, detail=str(exc),
                        )],
                    )

                meta_elem = opf_root.find(f".//{{{_OPF_NS}}}metadata")
                if meta_elem is None:
                    return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

                warnings: list[MetadataWarning] = []

                dc_title = meta_elem.findtext(f"{{{_DC_NS}}}title")
                title = dc_title.strip() if dc_title else None

                dc_publisher = meta_elem.findtext(f"{{{_DC_NS}}}publisher")
                publisher = dc_publisher.strip() if dc_publisher else None

                dc_language = meta_elem.findtext(f"{{{_DC_NS}}}language")
                if dc_language:
                    norm, changed = _normalise_language(dc_language.strip())
                    language = norm
                    if changed:
                        warnings.append(MetadataWarning(
                            code=WarningCode.LANGUAGE_NORMALISED,
                            detail=f"{dc_language.strip()} -> {norm}",
                        ))
                else:
                    language = None

                return BookMetadata(
                    title=title,
                    full_title=title,  # subtitle hunt added in Task 19
                    publisher=publisher,
                    language=language,
                    warnings=warnings,
                )
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_epub.py -v -k "title or publisher or language"
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/extractors/epub.py tests/test_metadata_epub.py
git commit -m "$(cat <<'EOF'
feat(metadata): EPUB OPF basics — title, publisher, language

dc:title, dc:publisher, dc:language with BCP-47 primary-subtag
normalisation (LANGUAGE_NORMALISED flag). Subsequent tasks add
creators, identifier, date, title-page fallback.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: EPUB — creators

**Goal:** Parse `<dc:creator>` with role detection (EPUB2 + EPUB3), file-as preference, trailing-punctuation handling, multi-creator strings, source order.

**Files:**
- Modify: `src/book_ingestion/extractors/epub.py`
- Modify: `tests/test_metadata_epub.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_epub.py`:

```python
from book_ingestion.metadata import CreatorRole


def test_epub_creator_with_role_aut(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "aut.epub",
        dc_title="X",
        creators=[("Finkelstein, Norman", "aut")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert len(m.creators) == 1
    assert m.creators[0].role == CreatorRole.AUTHOR
    assert m.creators[0].last_name == "Finkelstein"
    assert m.creators[0].first_name == "Norman"
    assert m.creators[0].raw == "Finkelstein, Norman"


def test_epub_creator_trailing_semicolon_flagged(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "ts.epub",
        dc_title="X",
        creators=[("Finkelstein, Norman; ", "aut")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.creators[0].last_name == "Finkelstein"
    assert m.creators[0].raw == "Finkelstein, Norman; "
    codes = {w.code for w in m.warnings}
    assert WarningCode.DC_CREATOR_TRAILING_PUNCTUATION in codes


def test_epub_creator_trailing_period_silent(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "tp.epub",
        dc_title="X",
        creators=[("Smith, J.", "aut")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.creators[0].last_name == "Smith"
    assert m.creators[0].first_name == "J"
    codes = {w.code for w in m.warnings}
    assert WarningCode.DC_CREATOR_TRAILING_PUNCTUATION not in codes


def test_epub_creator_role_translator(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "tr.epub",
        dc_title="X",
        creators=[("Translator, T.", "trl")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.creators[0].role == CreatorRole.TRANSLATOR


def test_epub_creator_multi_creator_in_one_string(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "multi.epub",
        dc_title="X",
        creators=[("Smith, J. and Jones, K.", "aut")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert [c.last_name for c in m.creators] == ["Smith", "Jones"]


def test_epub_creator_order_preserved(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "order.epub",
        dc_title="X",
        creators=[("Smith, Jane", "aut"), ("Jones, John", "aut")],
        isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert [c.last_name for c in m.creators] == ["Smith", "Jones"]
```

- [ ] **Step 2: Run, expect failure**

Expected: FAIL — `m.creators == []`.

- [ ] **Step 3: Implement creator extraction**

Update `src/book_ingestion/extractors/epub.py`:

```python
import re

from book_ingestion.metadata import Creator, CreatorRole

_OPF_ROLE_MAP: dict[str, CreatorRole] = {
    "aut": CreatorRole.AUTHOR,
    "edt": CreatorRole.EDITOR,
    "trl": CreatorRole.TRANSLATOR,
    "ill": CreatorRole.ILLUSTRATOR,
}


def _strip_creator_punct(raw: str) -> tuple[str, bool]:
    """Strip trailing whitespace + ; , and . from a creator string.

    Returns (stripped, flag_warning) — flag is True only when `;` or `,` was stripped.
    """
    s = raw
    flag = False
    # First trim trailing whitespace and periods silently
    while s and s[-1] in (" ", "\t", "."):
        s = s[:-1]
    # Then strip ; and , and flag
    while s and s[-1] in (";", ","):
        flag = True
        s = s[:-1]
    # Strip remaining trailing whitespace again
    s = s.rstrip()
    return s, flag


def _parse_one_creator_string(raw: str, role: CreatorRole) -> Creator:
    """Parse 'Last, First' or 'First Last' into a Creator. raw is preserved."""
    stripped, _ = _strip_creator_punct(raw)
    if "," in stripped:
        last, _, first = stripped.partition(",")
        last_name = last.strip() or None
        first_name = first.strip().rstrip(".") or None
    else:
        parts = stripped.rsplit(None, 1)
        if len(parts) == 2:
            first_name = parts[0].strip() or None
            last_name = parts[1].strip() or None
        else:
            first_name, last_name = None, stripped or None
    return Creator(role=role, first_name=first_name, last_name=last_name, raw=raw)


def _split_multi_creator(s: str) -> list[str]:
    """Split 'Smith, J. and Jones, K.' into ['Smith, J.', 'Jones, K.']."""
    return [p.strip() for p in re.split(r"\s+and\s+", s) if p.strip()]


def _extract_creators_from_opf(
    meta_elem: ET.Element,
    warnings: list[MetadataWarning],
) -> list[Creator]:
    """Walk dc:creator elements in document order; resolve role; split multi-creator strings."""
    creators: list[Creator] = []
    # Build EPUB3 refines map: id -> role (for <meta refines="#id" property="role">aut</meta>)
    refines_role: dict[str, str] = {}
    for meta in meta_elem.findall(f"{{{_OPF_NS}}}meta"):
        refines = meta.get("refines", "")
        if meta.get("property") == "role" and refines.startswith("#"):
            text = (meta.text or "").strip()
            if text:
                refines_role[refines[1:]] = text

    for elem in meta_elem.findall(f"{{{_DC_NS}}}creator"):
        text = elem.text or ""
        if not text.strip():
            continue
        # Resolve role
        role_str = elem.get(f"{{{_OPF_NS}}}role") or refines_role.get(elem.get("id", ""), "aut")
        role = _OPF_ROLE_MAP.get(role_str, CreatorRole.AUTHOR)

        # Prefer opf:file-as if present
        file_as = elem.get(f"{{{_OPF_NS}}}file-as")
        base_text = file_as if file_as else text

        # Punctuation flag
        _stripped, flag = _strip_creator_punct(base_text)
        if flag and not any(w.code == WarningCode.DC_CREATOR_TRAILING_PUNCTUATION for w in warnings):
            warnings.append(MetadataWarning(
                code=WarningCode.DC_CREATOR_TRAILING_PUNCTUATION,
                detail=f"creator '{text.strip()}' had trailing ; or ,",
            ))

        # Split multi-creator strings
        parts = _split_multi_creator(base_text)
        for i, part in enumerate(parts):
            # Preserve raw on the *first* parsed creator; multi-creators carry their split part as raw.
            raw_source = text if (i == 0 and not file_as and len(parts) == 1) else part
            creators.append(_parse_one_creator_string(raw_source, role))

    return creators
```

Call from `extract_metadata`:

```python
                creators = _extract_creators_from_opf(meta_elem, warnings)
                ...
                return BookMetadata(
                    title=title,
                    full_title=title,
                    publisher=publisher,
                    language=language,
                    creators=creators,
                    warnings=warnings,
                )
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_epub.py -v -k "creator"
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/extractors/epub.py tests/test_metadata_epub.py
git commit -m "$(cat <<'EOF'
feat(metadata): EPUB creators — roles, file-as, punctuation, multi, order

Spec §6.3: EPUB2 opf:role + EPUB3 refines/property=role both handled.
opf:file-as preferred over element text. Trailing ;, stripped + flagged;
trailing period stripped silently. Multi-creator strings split on
' and '. OPF element order preserved.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: EPUB — identifier (urn:isbn, meta isbn / eisbn)

**Goal:** Identifier extraction from `dc:identifier` and `<meta name="isbn"|"eisbn">`.

**Files:**
- Modify: `src/book_ingestion/extractors/epub.py`
- Modify: `tests/test_metadata_epub.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_epub.py`:

```python
from book_ingestion.metadata import EditionHint, IdentifierKind


def test_epub_extracts_print_isbn(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "isbn.epub",
        dc_title="X",
        creators=[],
        isbn="9780520295711",
        publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.identifier.kind == IdentifierKind.ISBN
    assert m.identifier.value == "9780520295711"


def test_epub_eisbn_in_candidates_with_ebook_hint(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "ei.epub",
        dc_title="X",
        creators=[],
        isbn="9780520295711",
        eisbn="9780520968431",
        publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.identifier.value == "9780520295711"
    eisbn_candidate = next(
        (c for c in m.identifier.candidates if c.value == "9780520968431"), None,
    )
    assert eisbn_candidate is not None
    assert eisbn_candidate.edition_hint == EditionHint.EBOOK


def test_epub_eisbn_only_becomes_value(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "eonly.epub",
        dc_title="X",
        creators=[],
        isbn=None,
        eisbn="9780520968431",
        publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.identifier.value == "9780520968431"
```

- [ ] **Step 2: Run, expect failure**

Expected: FAIL — `m.identifier.value is None`.

- [ ] **Step 3: Implement EPUB identifier extraction**

Add to `src/book_ingestion/extractors/epub.py`:

```python
from book_ingestion.metadata import (
    Identifier,
    IdentifierCandidate,
    IdentifierKind,
    canonicalize_isbn,
    dedupe_isbn_candidates,
    pick_identifier_value,
)


def _extract_identifier_from_opf(meta_elem: ET.Element) -> Identifier:
    raw_candidates: list[IdentifierCandidate] = []

    # dc:identifier with opf:scheme="ISBN" or urn:isbn: prefix
    for ident in meta_elem.findall(f"{{{_DC_NS}}}identifier"):
        text = (ident.text or "").strip()
        scheme = (ident.get(f"{{{_OPF_NS}}}scheme") or "").lower()
        is_isbn = False
        value = text
        if scheme == "isbn":
            is_isbn = True
        elif text.lower().startswith("urn:isbn:"):
            is_isbn = True
            value = text[len("urn:isbn:"):]
        if is_isbn:
            canon = canonicalize_isbn(value)
            raw_candidates.append(IdentifierCandidate(
                kind=IdentifierKind.ISBN, value=canon,
                edition_hint=EditionHint.UNSPECIFIED,
            ))

    # <meta name="isbn"> and <meta name="eisbn">
    for meta in meta_elem.findall(f"{{{_OPF_NS}}}meta"):
        name = (meta.get("name") or "").lower()
        content = meta.get("content") or ""
        if not content:
            continue
        if name == "isbn":
            raw_candidates.append(IdentifierCandidate(
                kind=IdentifierKind.ISBN, value=canonicalize_isbn(content),
                edition_hint=EditionHint.UNSPECIFIED,
            ))
        elif name == "eisbn":
            raw_candidates.append(IdentifierCandidate(
                kind=IdentifierKind.ISBN, value=canonicalize_isbn(content),
                edition_hint=EditionHint.EBOOK,
            ))

    if not raw_candidates:
        return Identifier()

    deduped = dedupe_isbn_candidates(raw_candidates)
    value = pick_identifier_value(deduped)
    return Identifier(
        kind=IdentifierKind.ISBN if value else None,
        value=value,
        candidates=deduped,
    )
```

Call from `extract_metadata`:

```python
                identifier = _extract_identifier_from_opf(meta_elem)
                ...
                return BookMetadata(
                    identifier=identifier,
                    title=title,
                    full_title=title,
                    publisher=publisher,
                    language=language,
                    creators=creators,
                    warnings=warnings,
                )
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_epub.py -v -k "isbn"
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/extractors/epub.py tests/test_metadata_epub.py
git commit -m "$(cat <<'EOF'
feat(metadata): EPUB identifier extraction

Spec §6.2: dc:identifier (urn:isbn: prefix or opf:scheme='ISBN'),
<meta name='isbn'> as print, <meta name='eisbn'> as candidate with
EBOOK hint. Reuses the M2.0 dedupe + priority helpers.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: EPUB — date selection

**Goal:** Pick `date` and `first_published` from `dc:date` events / EPUB3 properties / `dc:rights` fallback.

**Files:**
- Modify: `src/book_ingestion/extractors/epub.py`
- Modify: `tests/test_metadata_epub.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_epub.py`:

```python
def test_epub_date_with_publication_event(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "d.epub",
        dc_title="X", creators=[], isbn=None, publisher=None,
        language="en", date="2018",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.date == "2018"


def test_epub_date_from_rights_year_when_no_dc_date(tmp_path: Path) -> None:
    # build a custom OPF with dc:rights but no dc:date
    p = tmp_path / "rights.epub"
    opf = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="b">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>X</dc:title>
    <dc:language>en</dc:language>
    <dc:rights>Copyright © 2018 by Author</dc:rights>
  </metadata>
  <manifest><item id="t" href="t.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="t"/></spine>
</package>"""
    import zipfile as _zf
    with _zf.ZipFile(p, "w", _zf.ZIP_DEFLATED) as zf:
        zf.writestr(_zf.ZipInfo("mimetype"), "application/epub+zip", compress_type=_zf.ZIP_STORED)
        zf.writestr("META-INF/container.xml",
                    '<?xml version="1.0"?><container version="1.0" '
                    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                    '<rootfile full-path="OEBPS/content.opf" '
                    'media-type="application/oebps-package+xml"/></rootfiles></container>')
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/t.xhtml", "<html/>")

    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.date == "2018"
```

- [ ] **Step 2: Run, expect failure**

Expected: FAIL — `m.date is None`.

- [ ] **Step 3: Implement date selection**

Add to `src/book_ingestion/extractors/epub.py`:

```python
_YEAR_RE_EPUB = re.compile(r"\b(19|20)\d{2}\b")


def _extract_dates_from_opf(meta_elem: ET.Element) -> tuple[str | None, str | None]:
    """Return (date, first_published)."""
    publication: str | None = None
    original: str | None = None
    fallback: str | None = None

    for dc_date in meta_elem.findall(f"{{{_DC_NS}}}date"):
        event = (dc_date.get(f"{{{_OPF_NS}}}event") or "").lower()
        text = (dc_date.text or "").strip()
        if not text:
            continue
        if event == "publication":
            publication = text
        elif event == "original-publication":
            original = text
        elif fallback is None:
            fallback = text

    # EPUB3 meta refines/properties for dates
    for meta in meta_elem.findall(f"{{{_OPF_NS}}}meta"):
        prop = (meta.get("property") or "").lower()
        text = (meta.text or "").strip()
        if not text:
            continue
        if prop == "dcterms:issued" and publication is None:
            publication = text
        elif prop == "dcterms:created" and original is None:
            original = text

    if publication is not None or fallback is not None:
        date = publication or fallback
        return date, original

    # Fallback: extract a year from dc:rights
    dc_rights = meta_elem.findtext(f"{{{_DC_NS}}}rights")
    if dc_rights:
        m = _YEAR_RE_EPUB.search(dc_rights)
        if m:
            return m.group(0), None
    return None, original
```

Call from `extract_metadata`:

```python
                date, first_published = _extract_dates_from_opf(meta_elem)
                ...
                return BookMetadata(
                    identifier=identifier,
                    title=title,
                    full_title=title,
                    publisher=publisher,
                    language=language,
                    creators=creators,
                    date=date,
                    first_published=first_published,
                    warnings=warnings,
                )
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_epub.py -v -k "date"
```

Expected: PASS.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add src/book_ingestion/extractors/epub.py tests/test_metadata_epub.py
git commit -m "$(cat <<'EOF'
feat(metadata): EPUB date selection

Spec §6.4: dc:date with opf:event='publication' → date;
'original-publication' → first_published. EPUB3 meta property
'dcterms:issued' / 'dcterms:created' also handled. Falls back to year
from dc:rights.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 19: EPUB — title-page xhtml fallback (subtitle hunt)

**Goal:** When `dc:title` is bare, scan the title-page xhtml for a longer string and split off the subtitle.

**Files:**
- Modify: `src/book_ingestion/extractors/epub.py`
- Modify: `tests/test_metadata_epub.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_metadata_epub.py`:

```python
def test_epub_title_page_fallback_supplies_subtitle(tmp_path: Path) -> None:
    p = build_epub_with_truncated_title(
        tmp_path / "fallback.epub",
        dc_title="Gaza",
        full_title_in_xhtml="Gaza: An Inquest Into Its Martyrdom",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    assert m.title == "Gaza"
    assert m.subtitle == "An Inquest Into Its Martyrdom"
    assert m.full_title == "Gaza: An Inquest Into Its Martyrdom"
    codes = {w.code for w in m.warnings}
    assert WarningCode.SUBTITLE_NOT_IN_OPF in codes


def test_epub_title_page_no_fallback_when_dc_title_complete(tmp_path: Path) -> None:
    """If dc:title already contains a colon-delimited subtitle, don't fall back."""
    p = build_epub(
        tmp_path / "complete.epub",
        dc_title="Gaza: An Inquest Into Its Martyrdom",
        creators=[], isbn=None, publisher=None, language="en",
    )
    m = EpubMetadataExtractor().extract_metadata(p)
    # The extractor may parse "Gaza: An Inquest..." as title; subtitle handling
    # at the dc:title level is out of scope for M2.0 (just title=full string).
    # What matters: no SUBTITLE_NOT_IN_OPF warning.
    codes = {w.code for w in m.warnings}
    assert WarningCode.SUBTITLE_NOT_IN_OPF not in codes
```

- [ ] **Step 2: Run, expect failure**

Expected: FAIL on `test_epub_title_page_fallback_supplies_subtitle` — `m.subtitle is None`.

- [ ] **Step 3: Implement title-page fallback**

Add to `src/book_ingestion/extractors/epub.py`:

```python
def _find_title_page_href(opf_root: ET.Element, names: set[str]) -> str | None:
    """Return the EPUB-internal href of the title-page xhtml, or None."""
    # <guide type="title-page" href="..."/>
    for ref in opf_root.iter(f"{{{_OPF_NS}}}reference"):
        if (ref.get("type") or "").lower() == "title-page":
            return ref.get("href")
    for ref in opf_root.iter(f"{{{_OPF_NS}}}reference"):
        if (ref.get("type") or "").lower() == "cover":
            return ref.get("href")
    # Fallback: scan names for *itle*.xhtml or titlepage.xhtml
    for name in names:
        lowered = name.lower()
        if lowered.endswith(".xhtml") and ("titlepage" in lowered or "title" in lowered):
            return name
    return None


def _parse_title_page_text(xhtml_bytes: bytes) -> str | None:
    """Return the longest non-empty text in h1/h2/title from a title-page xhtml."""
    try:
        root = ET.fromstring(xhtml_bytes)
    except ET.ParseError:
        return None
    candidates: list[str] = []
    for tag in ("{http://www.w3.org/1999/xhtml}h1",
                "{http://www.w3.org/1999/xhtml}h2",
                "{http://www.w3.org/1999/xhtml}title"):
        for elem in root.iter(tag):
            text = "".join(elem.itertext()).strip()
            if text:
                candidates.append(text)
    if not candidates:
        return None
    return max(candidates, key=len)


def _split_subtitle(dc_title: str, full_candidate: str) -> tuple[str, str | None]:
    """If full_candidate contains dc_title as prefix + ':' or '—', split."""
    if not full_candidate.startswith(dc_title):
        return dc_title, None
    rest = full_candidate[len(dc_title):].lstrip()
    if rest and rest[0] in (":", "—", "-"):
        sub = rest[1:].strip()
        if sub:
            return dc_title, sub
    return dc_title, None
```

Wire into the OPF parse, after `title` is computed and before the return:

```python
                # Title-page xhtml fallback for subtitle
                subtitle: str | None = None
                if title is not None and ":" not in title and "—" not in title:
                    href = _find_title_page_href(opf_root, names)
                    if href is not None:
                        # Resolve href relative to the OPF file's directory
                        opf_dir = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""
                        candidate_path = f"{opf_dir}/{href}" if opf_dir else href
                        if candidate_path in names:
                            try:
                                xhtml_bytes = zf.read(candidate_path)
                                full_candidate = _parse_title_page_text(xhtml_bytes)
                            except KeyError:
                                full_candidate = None
                            if full_candidate is not None and full_candidate != title:
                                t2, sub = _split_subtitle(title, full_candidate)
                                if sub is not None:
                                    title = t2
                                    subtitle = sub
                                    warnings.append(MetadataWarning(
                                        code=WarningCode.SUBTITLE_NOT_IN_OPF,
                                        detail=f"subtitle from title-page xhtml: {sub}",
                                    ))

                full_title = (f"{title}: {subtitle}" if subtitle else title) if title else None
```

Update the return to use the new `subtitle` and `full_title`:

```python
                return BookMetadata(
                    identifier=identifier,
                    title=title,
                    subtitle=subtitle,
                    full_title=full_title,
                    publisher=publisher,
                    language=language,
                    creators=creators,
                    date=date,
                    first_published=first_published,
                    warnings=warnings,
                )
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/test_metadata_epub.py -v -k "title_page or complete"
```

Expected: PASS.

- [ ] **Step 5: Run full EPUB suite**

```bash
uv run pytest tests/test_metadata_epub.py -v
```

- [ ] **Step 6: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 7: Commit**

```bash
git add src/book_ingestion/extractors/epub.py tests/test_metadata_epub.py
git commit -m "$(cat <<'EOF'
feat(metadata): EPUB title-page xhtml fallback for subtitle

Spec §6.6: when dc:title contains no ':' or '—', search the OPF
<guide type='title-page'> (or 'cover', or *itle*.xhtml at root) for a
longer title and split the subtitle off. Flags SUBTITLE_NOT_IN_OPF.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 20: Public `extract_metadata` + dispatch + re-exports

**Goal:** Expose the function in `api.py`, wire the registry, and re-export from `__init__.py`.

**Files:**
- Modify: `src/book_ingestion/api.py`
- Modify: `src/book_ingestion/__init__.py`
- Create: `tests/test_metadata_api.py`

- [ ] **Step 1: Write failing tests**

`tests/test_metadata_api.py`:

```python
"""Tests for the public extract_metadata dispatch."""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion import BookMetadata, extract_metadata
from tests.fixtures.epub import build_epub
from tests.fixtures.pdf import build_pdf_with_imprint


def test_dispatch_to_pdf(tmp_path: Path) -> None:
    p = build_pdf_with_imprint(
        tmp_path / "x.pdf",
        title="X", subtitle="Y",
        isbn_paperback="9781234567897", isbn_hardback="9781234567880",
        publisher="P", places=["L"], year=2003,
    )
    m = extract_metadata(p)
    assert isinstance(m, BookMetadata)
    assert m.title == "X"


def test_dispatch_to_epub(tmp_path: Path) -> None:
    p = build_epub(
        tmp_path / "x.epub",
        dc_title="EpubBook", creators=[], isbn=None,
        publisher=None, language="en",
    )
    m = extract_metadata(p)
    assert isinstance(m, BookMetadata)
    assert m.title == "EpubBook"


def test_dispatch_propagates_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        extract_metadata(tmp_path / "does-not-exist.pdf")


def test_dispatch_rejects_unknown_extension(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("hi")
    with pytest.raises(ValueError):
        extract_metadata(p)


def test_pages_parameter_default_is_6(tmp_path: Path) -> None:
    """extract_metadata's signature should accept pages kw without raising."""
    p = build_pdf_with_imprint(
        tmp_path / "x.pdf",
        title="X", subtitle="Y",
        isbn_paperback="9781234567897", isbn_hardback="9781234567880",
        publisher="P", places=["L"], year=2003,
    )
    m = extract_metadata(p, pages=3)
    assert isinstance(m, BookMetadata)
```

- [ ] **Step 2: Run, expect ImportError**

```bash
uv run pytest tests/test_metadata_api.py -v
```

Expected: FAIL — `ImportError: cannot import name 'extract_metadata' from 'book_ingestion'`.

- [ ] **Step 3: Update `api.py`**

Add to `src/book_ingestion/api.py`:

```python
from book_ingestion.extractors.base import MetadataExtractor
from book_ingestion.extractors.epub import EpubMetadataExtractor
from book_ingestion.extractors.pdf import PdfMetadataExtractor
from book_ingestion.metadata import BookMetadata

_EXTRACTORS: dict[str, MetadataExtractor] = {
    "pdf": PdfMetadataExtractor(),
    "epub": EpubMetadataExtractor(),
}


def extract_metadata(path: Path, *, pages: int = 6) -> BookMetadata:
    """Extract frontmatter-shaped metadata from a book file.

    See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §3.
    """
    fmt = detect_format(path)
    if fmt not in _EXTRACTORS:
        raise ValueError(f"no metadata extractor registered for format: {fmt}")
    return _EXTRACTORS[fmt].extract_metadata(path, pages=pages)
```

- [ ] **Step 4: Update `__init__.py`**

Replace `src/book_ingestion/__init__.py` contents:

```python
"""book_ingestion — turn a book into a JSON IR."""

from book_ingestion.api import extract_chapter, extract_metadata, survey
from book_ingestion.ir import (
    SCHEMA_VERSION,
    BookSurvey,
    ChapterContent,
)
from book_ingestion.metadata import BookMetadata

__version__ = "0.1.0"

__all__ = [
    "SCHEMA_VERSION",
    "BookMetadata",
    "BookSurvey",
    "ChapterContent",
    "__version__",
    "extract_chapter",
    "extract_metadata",
    "survey",
]
```

- [ ] **Step 5: Run, expect pass**

```bash
uv run pytest tests/test_metadata_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Run all fast tests**

```bash
uv run pytest -m "not slow" -v
```

Expected: all green.

- [ ] **Step 7: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 8: Commit**

```bash
git add src/book_ingestion/api.py src/book_ingestion/__init__.py tests/test_metadata_api.py
git commit -m "$(cat <<'EOF'
feat(api): public extract_metadata function with format dispatch

Spec §3: extract_metadata(path, *, pages=6) -> BookMetadata, dispatched
via detect_format to PdfMetadataExtractor or EpubMetadataExtractor.
Re-exported from book_ingestion top-level alongside survey and
extract_chapter.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 21: Real-fixture acceptance — Holocaust Industry PDF

**Goal:** Pin expected outputs from a one-time exploratory run on the real fixture.

**Files:**
- Create: `tests/test_metadata_real.py`

The fixture lives at `/Users/rjl/Code/test-pdfs/The Holocaust Industry Reflections on the Exploitation of Jewish Suffering (Norman G. Finkelstein) (z-library.sk, 1lib.sk, z-lib.sk).pdf`. Mark `@pytest.mark.slow @pytest.mark.real_book`. Skip cleanly if the file isn't present.

- [ ] **Step 1: Run an exploratory extraction to pin values**

Manually:

```bash
uv run python -c "
from pathlib import Path
import json
from book_ingestion import extract_metadata
p = Path('/Users/rjl/Code/test-pdfs/The Holocaust Industry Reflections on the Exploitation of Jewish Suffering (Norman G. Finkelstein) (z-library.sk, 1lib.sk, z-lib.sk).pdf')
m = extract_metadata(p)
print(json.dumps(m.model_dump(mode='json'), indent=2))
"
```

Inspect the output. The test you'll write in Step 3 pins specific fields. If the output doesn't match the spec's expected values, **stop and fix the extractor**, not the test — this is the M2.0 acceptance gate.

- [ ] **Step 2: Write the acceptance test**

`tests/test_metadata_real.py`:

```python
"""Real-fixture acceptance tests for extract_metadata.

These tests depend on files at known paths outside the repo. Marked
@slow and @real_book so they're deselected from routine runs.

If a future spec change shifts a pinned value, the test fails and forces
the change to be reviewed — that's the regression signal.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from book_ingestion import extract_metadata
from book_ingestion.metadata import EditionHint, IdentifierKind, WarningCode

_HOLOCAUST_INDUSTRY_PATH = Path(
    "/Users/rjl/Code/test-pdfs/"
    "The Holocaust Industry Reflections on the Exploitation of Jewish "
    "Suffering (Norman G. Finkelstein) (z-library.sk, 1lib.sk, z-lib.sk).pdf"
)


@pytest.mark.slow
@pytest.mark.real_book
def test_holocaust_industry_pdf_acceptance() -> None:
    if not _HOLOCAUST_INDUSTRY_PATH.exists():
        pytest.skip(f"fixture missing: {_HOLOCAUST_INDUSTRY_PATH}")

    m = extract_metadata(_HOLOCAUST_INDUSTRY_PATH)

    # Identifier — pinned: paperback ISBN as the chosen value
    assert m.identifier.kind == IdentifierKind.ISBN
    assert m.identifier.value == "9781844674879"
    paperback = next(
        (c for c in m.identifier.candidates if c.edition_hint == EditionHint.PAPERBACK), None,
    )
    assert paperback is not None

    # Title — pinned: raw ALL-CAPS, no normalisation
    assert m.title is not None
    assert m.title.isupper()
    assert "HOLOCAUST INDUSTRY" in m.title

    # Subtitle — pinned: raw ALL-CAPS
    assert m.subtitle is not None
    assert m.subtitle.isupper()
    assert "EXPLOITATION" in m.subtitle

    # full_title composed
    assert m.full_title == f"{m.title}: {m.subtitle}"

    # Warnings
    codes = {w.code for w in m.warnings}
    assert WarningCode.TITLE_ALL_CAPS_IN_SOURCE in codes
    # ISBN-10 / ISBN-13 dedupe should keep MULTIPLE_ISBNS_DETECTED quiet
    assert WarningCode.MULTIPLE_ISBNS_DETECTED not in codes

    # Publication
    assert m.publisher == "Verso"
    assert m.places == ["London", "New York"]
    assert m.date == "2003"
    assert m.first_published == "2000"
```

- [ ] **Step 3: Run the slow real test**

```bash
uv run pytest tests/test_metadata_real.py -v -m "slow and real_book"
```

Expected: PASS. If it fails, inspect the assertion that failed:
- If the extractor is producing a worse value than the test pins, **fix the extractor**.
- If the spec's value is wrong on inspection (e.g., title actually starts mid-page), update both the spec and the test together in this commit.

- [ ] **Step 4: Re-run fast suite to ensure no regression**

```bash
uv run pytest -m "not slow" -v
```

Expected: still green.

- [ ] **Step 5: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 6: Commit**

```bash
git add tests/test_metadata_real.py
git commit -m "$(cat <<'EOF'
test(metadata): real-fixture acceptance — Holocaust Industry PDF

Spec §8.3. Pinned values from exploratory run: paperback ISBN-13 wins,
ALL-CAPS title + subtitle, Verso London+New York, 2003 / 2000.
Marked @slow @real_book; deselected from routine CI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 22: Real-fixture acceptance — Gaza EPUB

**Goal:** Pin expected outputs for the Gaza EPUB fixture.

**Files:**
- Modify: `tests/test_metadata_real.py`

The fixture lives at `/Users/rjl/Code/test-pdfs/Gaza - An Inquest Into Its Martyrdom (2018) (Norman Finkelstein) (z-library.sk, 1lib.sk, z-lib.sk).epub`.

- [ ] **Step 1: Exploratory run**

```bash
uv run python -c "
from pathlib import Path
import json
from book_ingestion import extract_metadata
p = Path('/Users/rjl/Code/test-pdfs/Gaza - An Inquest Into Its Martyrdom (2018) (Norman Finkelstein) (z-library.sk, 1lib.sk, z-lib.sk).epub')
m = extract_metadata(p)
print(json.dumps(m.model_dump(mode='json'), indent=2))
"
```

- [ ] **Step 2: Write the acceptance test**

Append to `tests/test_metadata_real.py`:

```python
_GAZA_EPUB_PATH = Path(
    "/Users/rjl/Code/test-pdfs/"
    "Gaza - An Inquest Into Its Martyrdom (2018) (Norman Finkelstein) "
    "(z-library.sk, 1lib.sk, z-lib.sk).epub"
)


@pytest.mark.slow
@pytest.mark.real_book
def test_gaza_epub_acceptance() -> None:
    if not _GAZA_EPUB_PATH.exists():
        pytest.skip(f"fixture missing: {_GAZA_EPUB_PATH}")

    m = extract_metadata(_GAZA_EPUB_PATH)

    # Identifier — print ISBN
    assert m.identifier.kind == IdentifierKind.ISBN
    assert m.identifier.value == "9780520295711"
    # eISBN as a candidate with EBOOK hint
    eisbn = next(
        (c for c in m.identifier.candidates if c.edition_hint == EditionHint.EBOOK), None,
    )
    assert eisbn is not None

    # Title / subtitle — fallback supplied the subtitle from title-page xhtml
    assert m.title == "Gaza"
    assert m.subtitle == "An Inquest Into Its Martyrdom"
    assert m.full_title == "Gaza: An Inquest Into Its Martyrdom"

    # Creator — Finkelstein, Norman with trailing punctuation in raw
    assert len(m.creators) == 1
    assert m.creators[0].last_name == "Finkelstein"
    assert m.creators[0].first_name == "Norman"
    assert m.creators[0].raw is not None
    assert m.creators[0].raw.endswith("; ") or m.creators[0].raw.endswith(";")

    # Language normalised
    assert m.language == "en"

    # Warnings pinned
    codes = {w.code for w in m.warnings}
    assert WarningCode.LANGUAGE_NORMALISED in codes
    assert WarningCode.DC_CREATOR_TRAILING_PUNCTUATION in codes
    assert WarningCode.SUBTITLE_NOT_IN_OPF in codes
```

- [ ] **Step 3: Run the slow real test**

```bash
uv run pytest tests/test_metadata_real.py::test_gaza_epub_acceptance -v
```

Expected: PASS. Same fix-the-extractor-not-the-test rule as Task 21.

- [ ] **Step 4: Run all slow tests together**

```bash
uv run pytest -m "slow and real_book" -v
```

Expected: both real-fixture tests pass.

- [ ] **Step 5: Run full fast suite**

```bash
uv run pytest -m "not slow" -v
```

Expected: all green; no regressions.

- [ ] **Step 6: Lint + type-check**

```bash
uv run ruff check src tests
uv run mypy
```

- [ ] **Step 7: Commit**

```bash
git add tests/test_metadata_real.py
git commit -m "$(cat <<'EOF'
test(metadata): real-fixture acceptance — Gaza EPUB

Spec §8.3. Pinned: print ISBN as value, eISBN as candidate with EBOOK
hint, dc:title='Gaza' + title-page-derived subtitle, single Finkelstein
creator with raw trailing '; ', language normalised en-US -> en,
three warnings (LANGUAGE_NORMALISED, DC_CREATOR_TRAILING_PUNCTUATION,
SUBTITLE_NOT_IN_OPF).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## After all tasks: integration smoke

Run the full test suite end-to-end:

```bash
uv run pytest -v                              # everything including slow
uv run ruff check src tests
uv run mypy
```

Expected:
- All fast tests green.
- Both `@slow @real_book` tests green (assuming fixtures present at the paths above).
- ruff clean.
- mypy clean.

If any of these fail, treat it as a regression and fix before declaring M2.0 done.

Post the plan-complete signal to skill via `.cowork/inbox/`:

```markdown
---
from: tool
to: skill
date: <today>
subject: M2.0 extract_metadata shipped
re: 0006-skill-to-tool-spec-review.md
---

M2.0 implemented and merged on `main`. All fast tests + both real-fixture
acceptance tests green. `extract_metadata` is importable from `book_ingestion`
and returns `BookMetadata` per the agreed shape.

You can integrate by calling:

```python
from book_ingestion import extract_metadata
m = extract_metadata("path/to/file.pdf")
m.model_dump(mode="json")   # the dict shape `adding-references` consumes
```

— tool
```

---

## Self-review (done before publishing this plan)

**Spec coverage check** — every section of the spec maps to at least one task:

| Spec section | Task(s) |
|---|---|
| §1 Scope (zero new deps) | Task 1, Task 7 (uses existing reportlab) |
| §2 Architecture / module layout | Task 1, Task 8, Task 14, Task 20 |
| §3 Public API + caller contract | Task 20 |
| §4.1 Closed vocabularies | Task 2 |
| §4.2 Sub-models | Task 3 |
| §4.3 BookMetadata top-level | Task 4 |
| §5.1 PDF pipeline | Task 8 (skeleton + early returns) |
| §5.2 PDF identifier extraction (incl. ISBN dedupe) | Task 5, Task 6, Task 9 |
| §5.3 PDF title / subtitle | Task 10 |
| §5.4 PDF creators | Task 11 |
| §5.5 PDF publisher / places / date / edition | Task 12 |
| §5.6 PDF language default 'en' | Task 12 |
| §6.1 EPUB pipeline | Task 14 |
| §6.2 EPUB identifier | Task 17 |
| §6.3 EPUB creators (incl. punctuation rule, source order) | Task 16 |
| §6.4 EPUB date selection | Task 18 |
| §6.5 EPUB language normalisation | Task 15 |
| §6.6 EPUB title-page fallback | Task 19 |
| §7 Error / warning runtime pattern | Task 8, Task 14, Task 15 (parse errors) |
| §8.1 Fast unit tests | Tasks 2, 3, 4, 5, 6 |
| §8.2 Synthetic-fixture integration | Tasks 7, 8–12, 13, 14–19 |
| §8.3 Real-fixture acceptance | Tasks 21, 22 |
| §8.4 Coverage targets | Implicit across Tasks 8–22 |

**No spec section is unmapped.**

**Placeholder scan:** no `TBD` / `TODO` / "similar to" patterns in the plan.

**Type / name consistency:** `BookMetadata`, `Identifier`, `IdentifierCandidate`, `Creator`, `MetadataWarning`, `IdentifierKind`, `EditionHint`, `CreatorRole`, `ErrorCode`, `WarningCode`, `MetadataExtractor`, `PdfMetadataExtractor`, `EpubMetadataExtractor`, `extract_metadata`, `canonicalize_isbn`, `isbn10_to_isbn13`, `dedupe_isbn_candidates`, `classify_edition_hint`, `pick_identifier_value` — all consistent across tasks.

**Scope check:** 22 tasks; each is self-contained with TDD steps. Plan is focused on M2.0; M2.1 deferred per spec §1.
