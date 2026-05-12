# book-ingestion M1.1 (Printed Page Labels) Implementation Plan

**Status:** plan, 2026-05-12
**Parent design spec:** [`../specs/2026-05-12-book-ingestion-design.md`](../specs/2026-05-12-book-ingestion-design.md)
**Branch:** `m1-pdf-mvp` (continues from `d120d3f`)
**Builds on:** M1 (Tasks 1–13 + fixes), already shipped

---

## Motivation

M1 surfaced a real product gap during real-book acceptance: every `page` field in the IR is a PDF page index (1-indexed position in the file), not the printed page number from the book. For citation-grade end uses, this is unusable as-is — citing "PDF page 18" is not equivalent to citing "page 14" of the printed work, and offsets vary per book and even per section within a book.

The design spec at §3.1 implies printed pages via its `"ch3, pp 142–145"` example. This phase closes that gap with a two-tier mechanism that mirrors the existing chapter-map provenance ladder (`embedded → inferred → none`).

## Approach

1. **Read PDF `/PageLabels` dictionary** via `pypdf` when present (exact, per-page; handles Roman/Arabic switches and mid-book restarts).
2. **Fall back to heuristic inference** from running-header/footer paragraph blocks already present in our IR (monotone numeric progression across consecutive pages).
3. **Bump IR `schema_version` to `"1.1"`** — additive only. Old M1 caches invalidate via `Cache._entry_valid` and re-populate transparently.
4. **Three new `KNOWN_FLAGS`**: `page_labels_embedded`, `page_labels_inferred`, `page_labels_unresolved`.

## IR shape (delta from M1)

- `SCHEMA_VERSION = "1.1"`
- `BookSurvey` gains `page_labels: dict[int, str] = {}` and `page_label_provenance: Literal["embedded", "inferred", "none"] = "none"`
- `PageRange` gains optional `start_page_label: str | None = None` and `end_page_label: str | None = None`
- Every block type that has a `page` field (`Paragraph`, `Heading`, `Table`, `FigureCaption`, `Footnote`, `PageBreak`, `FailedRegion`) gains `page_label: str | None = None`

All new fields default to `None` / `{}` / `"none"`, so existing tests and any pre-1.1 callers stay green.

## Task list

| # | Task | Touches |
|---|---|---|
| 1 | IR schema bump to 1.1 | `ir.py`, `quality/flags.py`, `tests/test_ir.py`, `tests/test_quality.py` |
| 2 | `page_labels` module — `/PageLabels` reader (pypdf) | `pyproject.toml`, `src/book_ingestion/page_labels.py`, `tests/test_page_labels.py` |
| 3 | `page_labels` module — heuristic inference | `src/book_ingestion/page_labels.py`, `tests/test_page_labels.py` |
| 4 | Projection accepts page-label map | `projection/to_simple_view.py`, `tests/test_projection.py` |
| 5 | PDF backend wires page labels | `backends/pdf_docling.py`, `tests/test_pdf_backend_survey.py` |
| 6 | Real-book regression | `tests/test_pdf_real.py` |

---

## Task 1: IR schema bump to 1.1

**Files:**
- Modify: `src/book_ingestion/ir.py`
- Modify: `src/book_ingestion/quality/flags.py`
- Modify: `tests/test_ir.py`
- Modify: `tests/test_quality.py`

**Step 1: Update IR**

In `src/book_ingestion/ir.py`:

- Change `SCHEMA_VERSION = "1.0"` to `SCHEMA_VERSION = "1.1"`.
- Extend `PageRange` with two optional fields after `end_page`:
  ```python
  start_page_label: str | None = None
  end_page_label: str | None = None
  ```
- Add `page_label: str | None = None` to **each** of: `Paragraph`, `Heading`, `Table`, `FigureCaption`, `Footnote`, `PageBreak`, `FailedRegion`. Place it immediately after the existing `page` field on each model.
- Extend `BookSurvey` with two fields, after `cache_paths`:
  ```python
  page_labels: dict[int, str] = Field(default_factory=dict)
  page_label_provenance: Literal["embedded", "inferred", "none"] = "none"
  ```

**Step 2: Update `KNOWN_FLAGS`**

In `src/book_ingestion/quality/flags.py`, add three entries to the frozenset under a new `# Page labels` section, keeping the existing comment-grouped structure:

```python
# Page labels
"page_labels_embedded",
"page_labels_inferred",
"page_labels_unresolved",
```

**Step 3: Update existing tests for the new fields**

In `tests/test_ir.py`, add the following test at the end of the file:

```python
def test_schema_version_is_one_one() -> None:
    """M1.1 bumps to 1.1 to invalidate older caches."""
    assert SCHEMA_VERSION == "1.1"


def test_page_range_with_labels_round_trips() -> None:
    from book_ingestion.ir import PageRange
    pr = PageRange(start_page=14, end_page=22, start_page_label="10", end_page_label="18")
    again = PageRange.model_validate(pr.model_dump(mode="json"))
    assert again == pr


def test_paragraph_with_page_label_round_trips() -> None:
    p = Paragraph(text="hi", page=14, page_label="10", confidence=Confidence.EXCELLENT)
    again = Paragraph.model_validate(p.model_dump(mode="json"))
    assert again == p
    assert again.page_label == "10"


def test_book_survey_with_page_labels_round_trips() -> None:
    survey = BookSurvey(
        schema_version=SCHEMA_VERSION,
        source=Source(path="/tmp/x.pdf", sha256="ab" * 32, size_bytes=1, format="pdf"),
        map=MapInfo(provenance=Provenance.EMBEDDED, confidence=Confidence.GOOD, method="pdf_outline"),
        quality=Quality(backend="docling_pdf", flags=[]),
        page_labels={1: "i", 2: "ii", 14: "10"},
        page_label_provenance="embedded",
    )
    again = BookSurvey.model_validate(survey.model_dump(mode="json"))
    assert again == survey
    assert again.page_labels[14] == "10"
    assert again.page_label_provenance == "embedded"
```

(Remove the old `test_schema_version_is_one_zero` test — it asserts the wrong constant now.)

Replace this line at the top of `test_ir.py`:
```python
def test_schema_version_is_one_zero() -> None:
    assert SCHEMA_VERSION == "1.0"
```
with the deletion (the new `test_schema_version_is_one_one` covers it).

In `tests/test_quality.py`, update the `expected` set in `test_known_flags_contains_expected` to include the 3 new entries.

**Step 4: Gates**

```bash
uv run pytest tests/test_ir.py tests/test_quality.py -v
uv run pytest tests/ -m "not slow"     # full fast suite must remain green
uv run ruff check src tests
uv run mypy
```

**Step 5: Commit**

```bash
git add src/book_ingestion/ir.py src/book_ingestion/quality/flags.py tests/test_ir.py tests/test_quality.py
git commit -m "feat(ir): bump schema_version to 1.1 with page_label fields"
```

---

## Task 2: page_labels module — `/PageLabels` reader (pypdf)

**Files:**
- Modify: `pyproject.toml` (add `pypdf>=5.0`)
- Create: `src/book_ingestion/page_labels.py`
- Create: `tests/test_page_labels.py`

**Step 1: Add dep**

Add `"pypdf>=5.0"` to the `dependencies` list in `pyproject.toml`, between the existing entries. Run `uv lock` to update the lock file.

**Step 2: Implement `read_pdf_page_labels`**

`src/book_ingestion/page_labels.py`:

```python
"""Printed page labels for PDFs.

Two paths:
  1. `read_pdf_page_labels()` — exact, reads the PDF /PageLabels dictionary.
  2. `infer_page_labels_from_blocks()` — heuristic, scans running headers/footers.

Both return a dict[int, str] mapping PDF page index (1-based) to printed label,
or None if no mapping could be produced.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_pdf_page_labels(path: Path) -> dict[int, str] | None:
    """Read the PDF /PageLabels dictionary via pypdf.

    Returns a dict mapping PDF page index (1-based, matching Docling's `page_no`)
    to the printed page label. Returns None if the PDF has no /PageLabels entry
    or if pypdf cannot parse the file.
    """
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        logger.warning("pypdf not installed; cannot read /PageLabels")
        return None

    try:
        reader = PdfReader(str(path))
    except (PdfReadError, OSError, ValueError) as exc:
        logger.warning("pypdf failed to read %s: %s", path, exc)
        return None

    # pypdf exposes `page_labels` as a list aligned to pages (0-indexed).
    # When /PageLabels is absent, pypdf falls back to "1","2",... which is
    # indistinguishable from genuine numeric labels — so we explicitly check
    # the /PageLabels entry in the catalog.
    root = reader.trailer.get("/Root") if reader.trailer else None
    catalog = root.get_object() if root is not None else None
    if catalog is None or "/PageLabels" not in catalog:
        return None

    labels: dict[int, str] = {}
    for i, page in enumerate(reader.pages, start=1):
        # pypdf 5.x: reader.page_labels[i-1] returns the label for that page.
        # We pull via the public API to avoid private-attribute coupling.
        try:
            label = reader.page_labels[i - 1]
        except (IndexError, KeyError, AttributeError):
            continue
        if label:
            labels[i] = str(label)
    return labels or None
```

**Step 3: Failing tests**

`tests/test_page_labels.py`:

```python
"""Tests for page-label extraction."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from book_ingestion.page_labels import read_pdf_page_labels


def _make_pdf_without_labels(path: Path) -> None:
    """Create a minimal 3-page PDF with no /PageLabels via ReportLab."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=LETTER)
    for n in range(3):
        c.drawString(72, 720, f"Page {n+1}")
        c.showPage()
    c.save()


def _make_pdf_with_labels(path: Path) -> None:
    """Build a 4-page PDF whose /PageLabels says: i, ii, 1, 2."""
    _make_pdf_without_labels(path)  # base 3-page; we'll pad to 4 below

    reader = PdfReader(str(path))
    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    # Add a 4th page so we have i, ii, 1, 2
    writer.add_blank_page(width=612, height=792)

    # /PageLabels: { /Nums [ 0 << /S /r >> 2 << /S /D >> ] }
    nums = ArrayObject([
        NumberObject(0),
        DictionaryObject({NameObject("/S"): NameObject("/r")}),  # roman lower
        NumberObject(2),
        DictionaryObject({NameObject("/S"): NameObject("/D")}),  # decimal
    ])
    page_labels = DictionaryObject({NameObject("/Nums"): nums})
    writer._root_object[NameObject("/PageLabels")] = page_labels  # noqa: SLF001 - test wiring

    with path.open("wb") as f:
        writer.write(f)


def test_returns_none_when_pdf_has_no_page_labels(tmp_path: Path) -> None:
    p = tmp_path / "no_labels.pdf"
    _make_pdf_without_labels(p)
    assert read_pdf_page_labels(p) is None


def test_returns_mapping_when_pdf_has_page_labels(tmp_path: Path) -> None:
    p = tmp_path / "with_labels.pdf"
    _make_pdf_with_labels(p)
    labels = read_pdf_page_labels(p)
    assert labels is not None
    # pypdf yields lowercase roman / arabic per the /S codes above
    assert labels[1] in {"i", "I"}
    assert labels[2] in {"ii", "II"}
    assert labels[3] == "1"
    assert labels[4] == "2"


def test_returns_none_on_malformed_pdf(tmp_path: Path) -> None:
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"not a pdf at all")
    assert read_pdf_page_labels(p) is None
```

**Step 4: Gates**

```bash
uv run pytest tests/test_page_labels.py -v   # expect 3 passed
uv run pytest tests/ -m "not slow"
uv run ruff check src tests
uv run mypy
```

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/book_ingestion/page_labels.py tests/test_page_labels.py
git commit -m "feat(page_labels): read /PageLabels from PDF via pypdf"
```

---

## Task 3: page_labels module — heuristic inference

**Files:**
- Modify: `src/book_ingestion/page_labels.py`
- Modify: `tests/test_page_labels.py`

**Step 1: Append the inference function to `page_labels.py`**

```python
import re

_ROMAN_LOWER = re.compile(r"^[ivxlcdm]+$")
_ROMAN_UPPER = re.compile(r"^[IVXLCDM]+$")
_ARABIC = re.compile(r"^\d+$")
_MIN_RUN = 4  # need at least 4 consecutive pages of agreement to infer

_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman_to_int(s: str) -> int | None:
    """Convert a Roman numeral to int. Returns None on bad input."""
    n = 0
    prev = 0
    for ch in reversed(s.lower()):
        v = _ROMAN_VALUES.get(ch)
        if v is None:
            return None
        n = n - v if v < prev else n + v
        prev = v
    return n if n > 0 else None


def _candidate_label(text: str) -> tuple[str, int] | None:
    """Pick a numeric or roman-numeral label out of a short header/footer line.
    Returns (label, integer_value) or None if no candidate found.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > 40:
        return None
    # Try whole-string match first
    if _ARABIC.match(stripped):
        return (stripped, int(stripped))
    if _ROMAN_LOWER.match(stripped) or _ROMAN_UPPER.match(stripped):
        v = _roman_to_int(stripped)
        if v is not None:
            return (stripped, v)
    # Fall back to first/last token
    for tok in (stripped.split()[0], stripped.split()[-1]):
        if _ARABIC.match(tok):
            return (tok, int(tok))
    return None


def infer_page_labels_from_blocks(
    page_texts: dict[int, list[str]]
) -> dict[int, str] | None:
    """Infer printed page labels from running-header/footer text.

    `page_texts` maps PDF page index → list of short text strings (typically
    the first and last few paragraph-block texts on that page; the caller
    decides what counts as a header/footer candidate).

    Returns a dict[int, str] when ≥ _MIN_RUN consecutive pages show a monotone
    integer progression in any candidate slot. Returns None otherwise.
    """
    if not page_texts:
        return None

    candidates: dict[int, list[tuple[str, int]]] = {}
    for page, texts in page_texts.items():
        page_candidates = [c for t in texts if (c := _candidate_label(t)) is not None]
        if page_candidates:
            candidates[page] = page_candidates

    # Try each candidate slot: for each consecutive sequence of pages, do the
    # integer values form `+1` arithmetic? If yes for ≥ _MIN_RUN, accept.
    sorted_pages = sorted(candidates.keys())
    if len(sorted_pages) < _MIN_RUN:
        return None

    # Find the longest run of consecutive PDF pages with monotone +1 labels.
    best: dict[int, str] = {}
    for slot_picker in (lambda cs: cs[0], lambda cs: cs[-1]):  # try first, then last token
        chosen: dict[int, tuple[str, int]] = {p: slot_picker(candidates[p]) for p in sorted_pages}
        # walk and detect runs
        run: list[int] = []
        for p in sorted_pages:
            label, val = chosen[p]
            if run and (p == run[-1] + 1) and (chosen[run[-1]][1] + 1 == val):
                run.append(p)
            else:
                run = [p]
            if len(run) >= _MIN_RUN and len(run) > len(best):
                best = {pp: chosen[pp][0] for pp in run}
        if best:
            break

    return best or None
```

**Step 2: Append tests to `tests/test_page_labels.py`**

```python
from book_ingestion.page_labels import infer_page_labels_from_blocks


def test_infer_arabic_progression() -> None:
    page_texts = {
        1: ["1", "Introduction"],
        2: ["chapter title", "2"],
        3: ["3", "more content"],
        4: ["4", "still more"],
        5: ["5", "etc"],
    }
    labels = infer_page_labels_from_blocks(page_texts)
    assert labels is not None
    assert labels[1] == "1"
    assert labels[5] == "5"


def test_infer_returns_none_when_no_signal() -> None:
    page_texts = {
        1: ["The quick brown fox", "jumps over"],
        2: ["the lazy dog", "and runs"],
        3: ["into the night", "alone"],
        4: ["forever", "and ever"],
    }
    assert infer_page_labels_from_blocks(page_texts) is None


def test_infer_requires_min_run_length() -> None:
    # Only 3 pages of progression, below threshold
    page_texts = {
        1: ["1"],
        2: ["2"],
        3: ["3"],
    }
    assert infer_page_labels_from_blocks(page_texts) is None


def test_infer_rejects_non_monotone() -> None:
    page_texts = {
        1: ["10"],
        2: ["5"],
        3: ["7"],
        4: ["12"],
    }
    assert infer_page_labels_from_blocks(page_texts) is None


def test_infer_finds_progression_inside_noisy_input() -> None:
    page_texts = {
        1: ["Front matter title"],
        2: ["acknowledgments"],
        3: ["preface"],
        4: ["1", "running header text"],
        5: ["2", "more"],
        6: ["3", "stuff"],
        7: ["4", "more stuff"],
        8: ["5", "etc"],
    }
    labels = infer_page_labels_from_blocks(page_texts)
    assert labels is not None
    assert labels[4] == "1"
    assert labels[8] == "5"
    # Front-matter pages without a numeric signal are absent from the map
    assert 1 not in labels
```

**Step 3: Gates**

```bash
uv run pytest tests/test_page_labels.py -v   # expect 8 passed (3 + 5)
uv run pytest tests/ -m "not slow"
uv run ruff check src tests
uv run mypy
```

**Step 4: Commit**

```bash
git add src/book_ingestion/page_labels.py tests/test_page_labels.py
git commit -m "feat(page_labels): heuristic inference from running headers/footers"
```

---

## Task 4: Projection accepts page-label map

**Files:**
- Modify: `src/book_ingestion/projection/to_simple_view.py`
- Modify: `tests/test_projection.py`

**Step 1: Extend projection signature**

In `src/book_ingestion/projection/to_simple_view.py`, change `project_to_simple_view` to accept an optional `page_labels` map and stamp `page_label` on each block whose page is in the map. Specifically:

```python
def project_to_simple_view(
    items: list[DoclingItem],
    *,
    page_labels: dict[int, str] | None = None,
) -> list[Block]:
    """Convert items to a list of simple_view blocks, inserting page_breaks
    between blocks that cross a page boundary. When `page_labels` is provided,
    each block's `page_label` is stamped from the map."""
    blocks: list[Block] = []
    last_page: int | None = None
    labels = page_labels or {}

    for item in items:
        if last_page is not None and item.page != last_page:
            page = item.page
            label = labels.get(page)
            blocks.append(PageBreak(page=page, page_label=label))
        last_page = item.page
        blocks.append(_project_one(item, label=labels.get(item.page)))

    return blocks
```

And update `_project_one` to accept a `label: str | None` keyword argument, threading it into every block constructor that takes `page_label` (which is all of them now per Task 1).

**Step 2: Tests**

Append the following test to `tests/test_projection.py`:

```python
def test_page_labels_stamped_when_map_provided() -> None:
    items = [
        _item("paragraph", text="On 14.", page=14),
        _item("paragraph", text="On 15.", page=15),
    ]
    labels = {14: "10", 15: "11"}
    blocks = project_to_simple_view(items, page_labels=labels)
    assert blocks[0].page_label == "10"
    assert blocks[1].page_label == "11"  # the synthetic PageBreak between them
    assert blocks[2].page_label == "11"
```

(The existing 9 tests will continue to pass because `page_labels=None` is the new default and every block already accepts `page_label=None` by default.)

**Step 3: Gates**

```bash
uv run pytest tests/test_projection.py -v   # expect 10 passed
uv run pytest tests/ -m "not slow"
uv run ruff check src tests
uv run mypy
```

**Step 4: Commit**

```bash
git add src/book_ingestion/projection/to_simple_view.py tests/test_projection.py
git commit -m "feat(projection): stamp page_label on blocks when map provided"
```

---

## Task 5: PDF backend wires page labels

**Files:**
- Modify: `src/book_ingestion/backends/pdf_docling.py`

**Step 1: Wire `_build_survey`**

Add imports at top of file:
```python
from book_ingestion.page_labels import (
    infer_page_labels_from_blocks,
    read_pdf_page_labels,
)
```

In `_build_survey`, after constructing `hints` and `chapters/map_info`, but before assembling the `BookSurvey`, compute the page-label map:

```python
# Try /PageLabels first (exact); fall back to heuristic inference; else 'none'.
labels: dict[int, str] | None = read_pdf_page_labels(path)
provenance: Literal["embedded", "inferred", "none"] = "none"
if labels:
    provenance = "embedded"
    flags.append("page_labels_embedded")
else:
    # Build a per-page text snapshot from the texts array for inference.
    page_snapshot: dict[int, list[str]] = {}
    for entry in docling["document"].get("texts") or []:
        if not isinstance(entry, dict):
            continue
        try:
            prov = entry.get("prov") or []
            if not prov or not isinstance(prov[0], dict) or "page_no" not in prov[0]:
                continue
            page = int(prov[0]["page_no"])
            text = str(entry.get("text") or "").strip()
            if text:
                page_snapshot.setdefault(page, []).append(text)
        except (TypeError, ValueError, KeyError):
            continue
    labels = infer_page_labels_from_blocks(page_snapshot)
    if labels:
        provenance = "inferred"
        flags.append("page_labels_inferred")
    else:
        flags.append("page_labels_unresolved")
for f in flags:
    validate_flag(f)
```

Then thread `labels` and `provenance` into the `BookSurvey(...)` call:

```python
return BookSurvey(
    schema_version=SCHEMA_VERSION,
    source=Source(...),
    metadata=...,
    chapters=_stamp_chapter_labels(chapters, labels or {}),
    map=map_info,
    quality=Quality(...),
    cache_paths={...},
    page_labels=labels or {},
    page_label_provenance=provenance,
)
```

And add a small static helper next to the existing adapters:

```python
@staticmethod
def _stamp_chapter_labels(
    chapters: list[Chapter], labels: dict[int, str]
) -> list[Chapter]:
    """Return chapters with start/end_page_label populated from `labels` when known."""
    stamped: list[Chapter] = []
    for c in chapters:
        if not isinstance(c.locator, PageRange):
            stamped.append(c)
            continue
        new_locator = c.locator.model_copy(update={
            "start_page_label": labels.get(c.locator.start_page),
            "end_page_label": labels.get(c.locator.end_page),
        })
        stamped.append(c.model_copy(update={"locator": new_locator}))
    return stamped
```

**Step 2: Wire `extract_chapter`**

In `extract_chapter`, after `survey = self.survey(path, ctx=ctx)`, pass `survey.page_labels` to projection:

```python
blocks = project_to_simple_view(items, page_labels=survey.page_labels or None)
```

**Step 3: Gates**

```bash
uv run pytest tests/ -m "not slow"               # full fast suite green
uv run pytest tests/test_pdf_backend_survey.py -v -m slow    # 2 passed
uv run pytest tests/test_pdf_backend_extract.py -v -m slow   # 2 passed
uv run ruff check src tests
uv run mypy
```

The existing slow tests do not assert on `page_labels` content but should not regress on structure or runtime.

**Step 4: Commit**

```bash
git add src/book_ingestion/backends/pdf_docling.py
git commit -m "feat(pdf): populate page_labels via /PageLabels reader + inference fallback"
```

---

## Task 6: Real-book regression

**Files:**
- Modify: `tests/test_pdf_real.py`

**Step 1: Add label assertions**

Append these assertions to `test_survey_returns_valid_book_survey`:

```python
    # M1.1: page labels must be populated (either embedded or inferred).
    assert s.page_label_provenance in {"embedded", "inferred", "none"}
    if s.page_label_provenance != "none":
        assert s.page_labels, "provenance says we have labels but the map is empty"
```

Append to `test_extract_each_detected_chapter`:

```python
        # Per-chapter locator labels are populated whenever the survey has labels
        if s.page_label_provenance != "none":
            assert isinstance(chapter.locator, PageRange)
            # Either both labels populated or both None (consistent state)
            start_lbl = chapter.locator.start_page_label
            end_lbl = chapter.locator.end_page_label
            assert (start_lbl is None) == (end_lbl is None)
```

**Step 2: Verify on the real book**

```bash
uv run pytest tests/test_pdf_real.py -v -m slow
```

Expected: 2 passed. Wall time ≤ 5 min on warm Docling cache.

Also run the full fast suite and lint pass:

```bash
uv run pytest tests/ -m "not slow"
uv run ruff check src tests
uv run mypy
```

**Step 3: Acceptance dump**

Wipe the previous acceptance cache (its `meta.json` schema_version is 1.0 — Cache.read will auto-invalidate, but a clean run is more transparent):

```bash
rm -rf acceptance/cache acceptance/*.json acceptance/*.stderr.log acceptance/*.md
mkdir -p acceptance
```

Then regenerate:

```bash
uv run book-ingest survey "test/What is Modern Israel (Yakov M. Rabkin) (z-library.sk, 1lib.sk, z-lib.sk).pdf" --cache-dir acceptance/cache > acceptance/survey.json
uv run book-ingest extract "test/What is Modern Israel (Yakov M. Rabkin) (z-library.sk, 1lib.sk, z-lib.sk).pdf" --chapter 8 --cache-dir acceptance/cache > acceptance/chapter-08.json
```

Verify the survey output:
- `page_label_provenance` is `"embedded"` (preferred) or `"inferred"` (acceptable fallback)
- `page_labels` map has ≥ 200 entries
- `chapters[8].locator.start_page_label == "10"` or whatever the printed label actually is at PDF page 14
- The label for the closing-sentence page (PDF 18, expected printed label "14") appears in any block on that page

**Step 4: Commit**

```bash
git add tests/test_pdf_real.py
git commit -m "test: assert page_labels populated on the real book"
```

---

## End-of-M1.1 checklist

- [ ] Fast suite passes
- [ ] Slow suite passes (incl. `test_pdf_real.py`)
- [ ] `acceptance/survey.json` has `page_label_provenance != "none"` and a non-empty `page_labels` map
- [ ] Chapter 8 (first body chapter) has `start_page_label = "10"` to confirm the +4 offset against PDF page 14 is closed
- [ ] `acceptance/README.md` updated to mention the new fields and the closed-loop validation

Once green, tag `v0.1.1-m1.1`.
