# book-ingestion — design specification

**Status:** draft 1, 2026-05-12
**Author:** Richard Lyon, with Claude (brainstorming pass)
**Input:** [`architecture.md`](../../../architecture.md) (statement of intent)
**Output:** this document (the design); implementation plan to follow via the `writing-plans` skill

---

## 1. Scope

`book_ingestion` is a Python 3.11+ library plus thin CLI that converts a local book file into a JSON intermediate representation (IR) consumed by a downstream LLM-driven workflow.

**In scope.**
- PDF parsing and clean text extraction (v1).
- EPUB parsing (v2).
- Scanned-PDF OCR fallback (v3).
- A chapter map with explicit provenance tags so the consumer knows how much to trust the partition.
- Per-block extraction with page-anchored locators.
- Honest, structured quality reporting at document, chapter, and block levels.
- One opt-in narrow LLM exception for chapter-structure inference (v4).

**Out of scope.** Authoring vault content; vault knowledge; fetching files; physical books; state between invocations beyond a content-hash cache; LLM calls in default operation; Zotero ↔ vault metadata reconciliation.

The consumer of this tool is the future `ingesting-books` skill (Path X in the upstream plan), which reads our JSON IR via shell and authors vault content itself.

## 2. Architecture

```
            ┌──────────────────────────────────────────────────┐
            │                       CLI                        │
            │   book-ingest survey <path>                      │
            │   book-ingest extract <path> --chapter <N>       │
            └──────────────────────┬───────────────────────────┘
                                   │ JSON to stdout
                                   ▼
            ┌──────────────────────────────────────────────────┐
            │                      api.py                      │
            │   survey(path) → BookSurvey                      │
            │   extract_chapter(path, idx) → ChapterContent    │
            └────────────┬────────────────────────┬────────────┘
                         │                        │
                         ▼                        ▼
              ┌────────────────┐        ┌──────────────────┐
              │   detect.py    │        │     cache.py     │
              │ format sniffer │        │  ~/.cache/...    │
              └────────┬───────┘        └──────────────────┘
                       │
          ┌────────────┴─────────────┬───────────────┐
          ▼                          ▼               ▼
   ┌─────────────┐         ┌──────────────────┐  ┌──────────┐
   │ pdf backend │ v1      │  epub backend    │  │ pdf_ocr  │
   │  (Docling)  │         │ (ebooklib+lxml)  │  │  v3      │
   └──────┬──────┘  v2     └──────────────────┘  └──────────┘
          │
          ▼
   ┌─────────────────────────────────────┐
   │ structure/  chapter map overlay     │
   │ quality/    confidence aggregation  │
   │ projection/ DoclingDocument →       │
   │             simple_view blocks      │
   └─────────────────────────────────────┘
```

**Approach (selected from three candidates during brainstorming).** Docling-driven, dual-IR projection. Docling is the PDF engine end-to-end in v1: we do not write our own layout analysis, header stripping, table reconstruction, or OCR. Our value-add layers on top of Docling's output:

1. A chapter map derived from Docling's outline and section hierarchy, tagged with provenance (`embedded` / `inferred` / `llm_assisted` / `none`) and a categorical confidence (`EXCELLENT` / `GOOD` / `FAIR` / `POOR`).
2. A projection from Docling's hierarchical tree into a flatter `simple_view` block list per chapter, with each block carrying page + confidence. This is the form the future EPUB backend will also emit, making the IR uniform across backends.
3. A standardized quality model that consumes Docling's `mean_grade` / `low_grade` and adds extraction-refusal flags where appropriate.
4. CLI, cache, and JSON IR so a skill (or future Path Y orchestrator) can drive it.

The two rejected approaches were a *thin facade over Docling* (loses uniform IR across PDF/EPUB) and a *backend-agnostic IR with multiple parsers* (over-engineered for a single likely-stable engine choice).

## 3. Intermediate representation

Both top-level shapes are Pydantic v2 models. `.model_dump()` serializes to JSON. Every payload carries a `schema_version` at the root for future migrations.

### 3.1 `BookSurvey` — returned by `survey()`

```jsonc
{
  "schema_version": "1.0",
  "kind": "book_survey",
  "source": {
    "path": "/abs/path/to/book.pdf",
    "sha256": "ab12…",
    "size_bytes": 4823104,
    "format": "pdf"
  },
  "metadata": {
    "title": "What is Modern Israel",
    "authors": ["Yakov M. Rabkin"],
    "publisher": null,
    "year": null,
    "isbn": null,
    "language": "en"
  },
  "chapters": [
    {
      "index": 0,
      "title": "Introduction",
      "locator": { "kind": "page_range", "start_page": 1, "end_page": 14 },
      "provenance": "embedded",
      "confidence": "EXCELLENT"
    }
  ],
  "map": {
    "provenance": "embedded",
    "confidence": "GOOD",
    "method": "pdf_outline"
  },
  "quality": {
    "backend": "docling_pdf",
    "docling_mean_grade": "GOOD",
    "docling_low_grade": "FAIR",
    "pages_total": 412,
    "pages_with_extraction_failures": 0,
    "flags": []
  },
  "cache_paths": {
    "docling_document": "/Users/.../sha256/docling.json"
  }
}
```

**Key shape decisions.**
- `locator` is a discriminated union. `kind: "page_range"` for PDFs (with `start_page` / `end_page`); `kind: "spine_range"` for EPUBs in v2 (with `start_spine` / `start_frag` / `end_spine` / `end_frag`).
- The skill formats the human-facing `cite_locator: "ch3, pp 142–145"` string itself from this structured data. The tool does not author display strings.
- `chapters[].confidence` is per-chapter; `map.confidence` is the document-level tier confidence. Both are categoricals matching Docling's grade enum.
- `cache_paths.docling_document` is a convenience pointer the skill (or a future audit tool) can `Read` if it wants deeper structural detail than `simple_view` provides.

### 3.2 `ChapterContent` — returned by `extract_chapter()`

```jsonc
{
  "schema_version": "1.0",
  "kind": "chapter_content",
  "source": { "path": "...", "sha256": "..." },
  "chapter": {
    "index": 3,
    "title": "Chapter 3 — Attribution",
    "locator": { "kind": "page_range", "start_page": 142, "end_page": 178 }
  },
  "simple_view": [
    { "type": "heading", "level": 1, "text": "Chapter 3 — Attribution", "page": 142, "confidence": "EXCELLENT" },
    { "type": "paragraph", "text": "...", "page": 142, "confidence": "EXCELLENT" },
    { "type": "heading", "level": 2, "text": "3.1 Detection", "page": 143, "confidence": "EXCELLENT" },
    { "type": "paragraph", "text": "...", "page": 143, "confidence": "EXCELLENT", "footnote_refs": ["fn-12"] },
    { "type": "table", "rows": [["...", "..."]], "page": 151, "confidence": "GOOD",
      "raw_text": "fallback unstructured text if rows are uncertain" },
    { "type": "figure_caption", "text": "Figure 3.2. ...", "page": 152, "confidence": "GOOD" },
    { "type": "footnote", "id": "fn-12", "text": "...", "page": 145, "confidence": "GOOD" },
    { "type": "page_break", "page": 153 },
    { "type": "failed_region", "page": 167, "reason": "ocr_low_confidence",
      "raw_text": "garbled text — NOT to be quoted verbatim" }
  ],
  "quality": {
    "backend": "docling_pdf",
    "pages_processed": [142, 143],
    "pages_with_failures": [167],
    "block_confidence_counts": { "EXCELLENT": 42, "GOOD": 18, "FAIR": 3, "POOR": 1 },
    "flags": ["ocr_low_confidence_block"]
  },
  "docling_document": null,
  "cache_paths": {
    "docling_chapter": "/Users/.../sha256/chapter-3.docling.json"
  }
}
```

**Block types in `simple_view`.**

| Type | Fields | Notes |
|---|---|---|
| `paragraph` | `text`, `page`, `confidence`, optional `footnote_refs`, optional `list_marker`, optional `continued_from` | Lists are flattened into paragraphs with a `list_marker` field; we do not introduce a separate `list` block, keeping `simple_view` shallow |
| `heading` | `text`, `level` (1–6), `page`, `confidence` | |
| `table` | `page`, `confidence`, `rows: list[list[str]]` when GOOD or better, `raw_text` always | When table_score is POOR or FAIR, `rows` is omitted and only `raw_text` is provided |
| `figure_caption` | `text`, `page`, `confidence` | Figures themselves are not vault content; only captions are extracted |
| `footnote` | `id`, `text`, `page`, `confidence` | Referenced by `footnote_refs` on paragraph blocks |
| `page_break` | `page` | Zero-content sentinel marking a page transition. Following paragraphs are not concatenated across this break |
| `failed_region` | `page`, `reason`, optional `raw_text` | Explicit refusal-to-extract. `raw_text` may be present for audit but is not safe to quote |

A paragraph that physically spans two pages in the source is split at the page break and emitted as two paragraph blocks; the second carries `continued_from: <id of first>`. The skill can re-join them if it wants, but the default reading is page-anchored.

The `failed_region` block is the linchpin of "honesty over completeness" (architecture §3.3). Any extraction the tool is not confident in becomes a `failed_region`, never a normal paragraph.

**The `docling_document` field is always `null` inline.** The raw DoclingDocument subtree for the chapter is never embedded directly in the `ChapterContent` JSON (it would bloat the payload). It is always written to disk and pointed at via `cache_paths.docling_chapter`. The skill reads it with the `Read` tool only when it needs detail beyond `simple_view` (e.g. complex nested structure in tables, layout audit). EPUB and other future backends that do not produce a DoclingDocument leave both `docling_document: null` and `cache_paths.docling_chapter` absent; the skill checks `cache_paths.docling_chapter` presence to know whether the rich view is available.

## 4. Public surface

### 4.1 CLI

Three subcommands. JSON to stdout. Logs to stderr. Exit codes:
- `0` — success, JSON usable.
- `2` — extraction refused (e.g. `map.provenance: "none"`, or every chapter block is `failed_region`). JSON is still written; the skill should pause.
- `1` — hard error (file not found, unsupported format, unhandled exception). Error JSON on stderr; no payload on stdout.

```bash
book-ingest survey <path>                     # fast; populates chapter map and triggers Docling parse (cached)
book-ingest survey <path> --llm-assist         # opt-in chapter-structure inference (v4)
book-ingest survey <path> --no-cache           # force re-parse

book-ingest extract <path> --chapter <N>       # extract one chapter (N is the index from survey)
book-ingest extract <path> --chapter <N> --no-cache

book-ingest cache list
book-ingest cache clear <path>
book-ingest cache clear --all
```

**Global flags.**
- `--cache-dir <PATH>` overrides default `~/.cache/book-ingestion/`.
- `--quiet` / `--verbose` adjust log level (stderr).
- `--json-schema {survey,extract}` emits the JSON schema for one IR shape (skill authors use this for prompt construction).

### 4.2 Library

```python
from book_ingestion import survey, extract_chapter
from book_ingestion.ir import BookSurvey, ChapterContent

result: BookSurvey = survey(
    path: Path,
    *,
    cache_dir: Path | None = None,
    use_cache: bool = True,
    llm_assist: bool = False,
)

content: ChapterContent = extract_chapter(
    path: Path,
    chapter_index: int,
    *,
    cache_dir: Path | None = None,
    use_cache: bool = True,
)
```

Both functions are deterministic given the same input and cache state, and have no global side effects beyond cache reads and writes. They are safe to call from any orchestrator.

### 4.3 Errors as values at the boundary

Inside the library, exceptions are used normally. At the public API boundary, **predictable failures become typed fields in the IR**, not exceptions:

| Failure | Boundary handling |
|---|---|
| Unparseable file | `BookSurvey` with `map.provenance: "none"`, `quality.flags: ["unparseable"]`, exit code 2 |
| One bad page in an otherwise-good chapter | `failed_region` block in `simple_view`, chapter still returned, exit code 0 |
| Chapter index out of range | `ValueError` raised in Python; CLI catches and exits 1 with stderr error |
| File not found | `FileNotFoundError`; CLI exits 1 |

## 5. Backends

### 5.1 Backend registry

```python
class Backend(Protocol):
    def survey(self, path: Path, *, ctx: Context) -> BookSurvey: ...
    def extract_chapter(self, path: Path, idx: int, *, ctx: Context) -> ChapterContent: ...

REGISTRY: dict[str, Backend] = {
    "pdf":      PdfBackend(),       # v1, Docling
    # "epub":   EpubBackend(),       # v2
    # "pdf_ocr": OcrBackend(),       # v3
}
```

`detect.py` sniffs format by extension + magic bytes and routes to the right backend. v1 supports PDF only. v2 adds EPUB. v3 adds the OCR path: PDFs whose text layer is missing (or has fewer than a threshold glyph count) are routed to `pdf_ocr` instead of `pdf`.

### 5.2 PDF backend (v1, Docling-driven)

```python
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat

def _converter() -> DocumentConverter:
    opts = PdfPipelineOptions(
        do_ocr=False,                     # v1 digital; v3 flips this for the OCR backend
        do_table_structure=True,
        generate_picture_images=False,
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
```

**`survey()` flow.**
1. Hash file (sha256). If the DoclingDocument is cached for that hash, skip Docling.
2. Otherwise run Docling once, write `docling.json` to the cache.
3. Build the chapter map: try the embedded PDF outline first (via Docling's exposed structure); fall back to typographic inference (`structure/typographic.py`); fall back to `provenance: "none"` if both fail.
4. Aggregate `doc.confidence` into `quality`.
5. Read file-level metadata. Docling exposes some; ISBN/year may need a secondary pull from the PDF `/Info` dictionary (open issue, may degrade to nulls).
6. Return `BookSurvey`.

**`extract_chapter(idx)` flow.**
1. Load cached DoclingDocument (or run Docling now if absent).
2. Identify the subtree for chapter `idx` from the chapter map.
3. Walk the subtree in reading order, projecting each Docling item into a `simple_view` block (see 5.3).
4. Write `chapter-{idx}.docling.json` (slice of the document, for `cache_paths.docling_chapter`).
5. Aggregate per-chapter quality.
6. Return `ChapterContent`.

### 5.3 Projection: `DoclingDocument` → `simple_view`

Implemented in `projection/to_simple_view.py`. Mapping:

| Docling item | `simple_view` block | Notes |
|---|---|---|
| `SectionHeaderItem` | `heading` (level from depth) | Also used as chapter boundaries |
| `TextItem(label=PARAGRAPH)` | `paragraph` | Page from `prov[0].page_no` |
| `TextItem(label=LIST_ITEM)` | `paragraph` with `list_marker` field | No separate `list` block — keeps `simple_view` shallow |
| `TableItem` | `table` with `rows` if `table_score >= GOOD`, else `raw_text` only | |
| `PictureItem` + caption | `figure_caption` | Picture itself is discarded |
| `TextItem(label=FOOTNOTE)` | `footnote` block with stable ID; `[^fn-N]` marker inserted in the referring paragraph; ID added to `footnote_refs` on that paragraph | |
| Page transition | synthetic `page_break` block | Inserted between blocks whose `prov.page_no` differs |
| Low-confidence page (`page_score == POOR`) or unicode-normalization failure region | `failed_region` block | Raw text held aside in `raw_text` for audit |

**Invariants the projection upholds.**
- We never invent text Docling did not produce.
- We never concatenate paragraph text across a page break in the projection (the skill may re-join via `continued_from`).
- We never silently drop content: a Docling item that does not map to a known type is emitted as `failed_region` with `reason: "unknown_item_type"`.

### 5.4 EPUB backend (v2 stub)

Outline only; implemented in v2.
- EbookLib parses spine + nav. lxml walks each spine item's XHTML.
- Output uses the same `simple_view` shape, with `page` from EPUB3 `page-list` when present (hand-parsed from the nav document — EbookLib does not expose it directly), otherwise omitted.
- `docling_document: null` in the JSON output; the skill checks `cache_paths` presence instead.
- Chapter map comes from the EPUB nav (`toc.ncx` for EPUB2 or `nav.xhtml` for EPUB3). Provenance `embedded`; we do not attempt typographic inference on EPUBs.

### 5.5 OCR backend (v3 stub)

When `detect.py` finds a PDF without a usable text layer, route to `pdf_ocr`. Implementation calls Docling with `do_ocr=True` (Tesseract by default; Surya / RapidOCR optional). Per-block confidence reflects OCR scores. If `low_grade == POOR` for the whole document, the survey returns `quality.flags = ["ocr_severely_degraded"]` and exit code 2.

## 6. Caching, quality, and error handling

### 6.1 Cache

Default location: `~/.cache/book-ingestion/<sha256-of-file>/`. Overridable via `--cache-dir` or `cache_dir=`.

```
~/.cache/book-ingestion/<sha256>/
  meta.json                  # path-of-origin, file size, format, schema_version, created_at
  docling.json               # full DoclingDocument (lossless) — written on first survey
  survey.json                # the BookSurvey returned to the caller
  chapter-0.json             # ChapterContent IR (what extract_chapter returns)
  chapter-0.docling.json     # raw DoclingDocument slice for chapter 0 (the cache_paths.docling_chapter pointer)
  chapter-1.json
  chapter-1.docling.json
  ...
```

**Invariants.**
- Cache key is the sha256 of file *content*, not path. Moving a book leaves the cache valid.
- `meta.json` records `schema_version`. On read, mismatched versions invalidate the entry transparently (logged at INFO).
- `--no-cache` reads ignore the cache but still write fresh entries (so the next call benefits).
- The cache is opaque to the caller. `cache_paths.*` in the IR is a convenience pointer; callers must never write into the cache.

**Concurrency.** v1 is single-process and does no locking. Two racing `survey` calls on the same file produce identical content (Docling is deterministic given the same input), so the loser simply overwrites. v2 may add an advisory `.lock` if it becomes a real problem.

### 6.2 Quality model

Three layers feed the `quality` field in both IR shapes:

**(a) Docling-native, surfaced as-is.**
- Document-level `mean_grade` and `low_grade` → `quality.docling_mean_grade` / `quality.docling_low_grade`.
- Page-level `layout_score`, `ocr_score`, `parse_score`, `table_score` (the last not yet implemented in Docling) → consulted when assigning per-block `confidence`. Not all emitted into the IR (would bloat the payload).
- Per-block grade: one of `EXCELLENT | GOOD | FAIR | POOR`, derived from page-level scores at the block's page.

**(b) Our overlays.** Computed in `quality/flags.py`:
- `pages_with_extraction_failures` (count, document level).
- `block_confidence_counts` (histogram per chapter).
- Free-form `flags`, vocabulary kept small and documented in `quality/flags.py`'s `KNOWN_FLAGS` set:
  - `ocr_used`, `ocr_low_confidence_block`, `ocr_severely_degraded`
  - `two_column_layout`, `mixed_layout`
  - `embedded_toc_present`, `toc_inferred`, `toc_unresolved`
  - `tables_present`, `table_structure_uncertain`
  - `unicode_normalization_failure`
  - `llm_assist_used`
- New flag = new entry in `KNOWN_FLAGS` + an inline comment explaining what condition produces it.

**(c) Provenance.** Computed in `structure/`:
- `chapters[].provenance ∈ {embedded, inferred, llm_assisted, none}`.
- `map.provenance` = worst-case across chapters (any `none` forces `map=none`).

### 6.3 Error handling and refusal posture

| Regime | Example | Response | Exit |
|---|---|---|---|
| Whole-document failure | No chapters detectable, every page POOR | `BookSurvey` with `map.provenance: "none"` and full quality flags. Skill expected to pause | 2 |
| Region-level failure | One garbled page; one table with uncertain structure | Inline `failed_region` or `table { raw_text only }`; rest of chapter returned normally | 0 |
| Hard error | File not found, unhandled exception | JSON-shaped error on stderr; no payload on stdout | 1 |

The single invariant the spec is built around: **an LLM reading our JSON can never end up quoting unreliable text as reliable.** Every uncertain extraction is *typed* as uncertain (`failed_region`, `confidence: POOR`, `flags: [...]`) so the consumer's reading-comprehension burden is "check these typed fields", not "use judgment over prose."

## 7. Project layout

```
book-ingestion/
  pyproject.toml          # uv + hatchling, version pins per §9
  README.md               # install (incl. ocrmypdf system deps in v3), API, examples
  architecture.md         # the spec input (this file's parent)
  docs/superpowers/specs/ # design specs (this file lives here)
  src/book_ingestion/
    __init__.py           # exports survey, extract_chapter, BookSurvey, ChapterContent
    api.py                # public surface; orchestrates backend selection + cache
    ir.py                 # Pydantic v2 models; schema_version constant
    cli.py                # Typer app
    cache.py              # disk cache, content-hash keyed
    detect.py             # format/backend sniffing
    backends/
      __init__.py         # registry
      base.py             # Backend Protocol
      pdf_docling.py      # v1
      epub.py             # v2 stub initially
      pdf_ocr.py          # v3 stub initially
    projection/
      __init__.py
      to_simple_view.py   # DoclingDocument → simple_view blocks
    structure/
      __init__.py
      embedded_toc.py     # PDF outline / EPUB nav extraction
      typographic.py      # heuristic chapter inference
      llm_assist.py       # opt-in narrow LLM call (v4)
    quality/
      __init__.py
      flags.py            # KNOWN_FLAGS, flag-emission rules
      scoring.py          # Docling-scores → block confidence
  tests/
    conftest.py
    fixtures/
      _synth/             # ReportLab-generated synthetic fixtures
      arxiv-preprint.pdf  # public CC-BY (bundled if license allows; else download script)
    test_smoke.py         # < 5s gate (synthetic 1-page PDF)
    test_projection.py    # unit on projection
    test_structure.py     # unit on chapter-map building
    test_quality.py       # unit on flag emission
    test_cache.py         # unit on cache round-trip + schema-version invalidation
    test_pdf_real.py      # integration vs the real book in ../test/ (slow)
    test_pdf_arxiv.py     # integration vs the bundled arXiv fixture (slow)
    snapshots/            # syrupy snapshots
```

## 8. Testing

**Three tiers.**

**(a) Unit tests** — pure functions on synthetic inputs.
- `projection/to_simple_view.py`: hand-crafted minimal `DoclingDocument` objects → exact `simple_view` output. Tests cover paragraph split at page break, footnote ID linking, table fallback to `raw_text` when confidence is FAIR or worse, list-marker handling, unknown-item-type emitted as `failed_region`.
- `structure/typographic.py`: synthetic font-run sequences → expected chapter inferences.
- `quality/flags.py`: known input scores → expected flag emission; `KNOWN_FLAGS` enforcement.
- `cache.py`: round-trip serialization, schema-version invalidation, content-hash keying.
- Fast (under 2 s total), deterministic, no network, no Docling.

**(b) Integration tests** — Docling against fixture files, using `syrupy` for snapshots.
- Fixtures (v1 ships PDF only):
  - **`test/What is Modern Israel (Yakov M. Rabkin) (z-library.sk, 1lib.sk, z-lib.sk).pdf`** — the real book Richard has placed in the project root's `test/` folder. Primary smoke fixture for the M1 end-to-end demo. Tagged `@pytest.mark.real_book` and `@pytest.mark.slow`.
  - A short arXiv preprint (CC-BY), bundled or downloaded by a `tests/fixtures/_download.py` script.
  - A synthesized two-column PDF generated by ReportLab at test time (deterministic).
- Snapshots cover: the full chapter map, the full `quality` block, and per-chapter first-paragraph-text + block-count + flag-list. Not full text — keeps snapshot churn manageable.
- Marked `@pytest.mark.slow`, run on demand and in CI nightly.

**(c) Smoke test** — under 5 s, the gate before every commit.
- A 1-page synthetic PDF (3 paragraphs) generated by a `conftest.py` factory. Asserts that `survey` returns one chapter and `extract_chapter(0)` returns 3 paragraph blocks at `confidence: EXCELLENT`.

**End-of-M1 acceptance.** Run `book-ingest survey test/What\ is\ Modern\ Israel...pdf` followed by `book-ingest extract … --chapter N` for each detected chapter. Acceptance is manual review of:
- Chapter titles are correct.
- Page ranges look plausible.
- The first paragraph of each chapter starts in the right place in the source.
- No `failed_region` blocks unless visually justified in the source PDF.

## 9. Dependencies and tooling

All version pins reflect releases verified on PyPI as of 2026-05-12.

**Required (M1).**
- `docling >= 2.93` (2026-05-07; Python ≥3.10)
- `pydantic >= 2.13` (2026-05-06)
- `typer >= 0.25` (2025-04-30; note the slower release cadence vs other deps — Click is the documented fallback)

**Required (M2).**
- `ebooklib >= 0.20` (released 2024-10-26; format is stable but cadence is slow — if EbookLib goes truly dead before v2 ships, fall back to a hand-rolled lxml-based EPUB walker)
- `lxml >= 6.1` (2026-04-18; recent XXE-default tightening)

**Optional extras (declared in `pyproject.toml`).**
- `book-ingestion[llm]` → `anthropic >= 0.101` (2026-05-11) — used by `structure/llm_assist.py` when `--llm-assist` is set.
- `book-ingestion[dev]` → development tooling, see below.

**Dev tooling.**
- `pytest >= 9.0` (2026-04-07; note the 9.x major-version transition)
- `syrupy >= 5.1` (2026-01-26) — chosen over `pytest-snapshot` because syrupy fails on *missing* snapshots, not just on diffs. This aligns with the spec's "no silent corruption" posture: a new IR field that someone forgets to snapshot would fail loudly.
- `ruff >= 0.15` (2026-04-24)
- `mypy >= 2.1` (2026-05-11; note the 2.x major-version transition)
- `reportlab >= 4.5` (2026-05-12; BSD-licensed; used to generate synthetic PDF fixtures deterministically)

**Excluded by design.**
- `pymupdf` — superseded by Docling. AGPL-licensed.
- `pdf-craft` — Markdown/EPUB-only output makes it a poor fit for JSON IR. Documented as an external salvage path the user runs manually if a scan is catastrophically degraded.
- `layoutparser`, `transformers`, `torch` direct dependencies — all transitively managed by Docling.

**Build tooling.**
- `uv >= 0.11` for venv, lockfile, and script running.
- `hatchling >= 1.29` as the build backend (Pydantic, FastAPI, and many others use it; uv plays nicely).
- Python 3.11+ (Docling requires 3.10+; 3.11 gets us `tomllib`, `Self`, and exception groups).

**License.** MIT, matching Docling, EbookLib, pdf-craft, and the broader open-source PDF ecosystem.

**Repo location.** `/Users/rjl/Code/gitea/book-ingestion`, Gitea-hosted.

## 10. Milestones

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 — PDF MVP** | Docling backend, IR + projection, CLI (`survey`/`extract`/`cache`), content-hash cache, quality reporting, smoke + integration tests | End-to-end run on `test/What is Modern Israel…pdf` produces a sensible chapter map and `simple_view`; arXiv fixture passes snapshot tests |
| **M2 — EPUB** | EpubBackend (EbookLib + lxml), EPUB3 `page-list` hand-parsing, EPUB fixtures (Standard Ebooks + Project Gutenberg) | Both EPUB fixtures pass snapshot tests; `simple_view` shape is uniform with M1 |
| **M3 — OCR fallback** | `pdf_ocr` backend (Docling with `do_ocr=True`), text-layer detection in `detect.py`, `ocr_*` quality flags, scanned-PDF fixture | Rasterized version of the arXiv fixture survives extraction with appropriately degraded confidence |
| **M4 — Hardening + LLM-assist** | `structure/llm_assist.py` behind `--llm-assist`, edge-case fixtures (parts→chapters→sections, dual-column policy report), README + skill-author docs | Adversarial fixtures handled or refused with `provenance: "none"` |

M1 should land in roughly a week of focused work. M2 a few days. M3 a few days. M4 ongoing as real books reveal edge cases.

## 11. Risks and open questions

1. **Docling outline access API.** Surveys depend on Docling exposing the PDF outline / section hierarchy in a stable form. Docling 2.x has it, but the exact accessor path may have changed since the docs I read. Verify in the M1 first commit.
2. **Paragraph-page-split correctness.** Some Docling paragraphs span page breaks. The projection's split-and-continued_from approach is unverified against real Docling output; may need refinement against the test book.
3. **Two-column reflow correctness on policy reports.** Docling claims layout-awareness; the failure mode on mixed-layout pages (one column on cover, two on body) is unknown. Will surface during M4 fixture work.
4. **Footnote ID stability.** Docling's reference model may or may not preserve a stable footnote ID across paragraphs and the footnote block. If not, we synthesize IDs in projection. Document in M1.
5. **EPUB without `page-list`.** Print page numbers genuinely don't exist for reflowed EPUBs. The IR honors this by omitting `page` on those blocks; the skill must accept `(chapter, paragraph-index)` locators for such books. Document in M2.
6. **EbookLib maintenance.** Last release 19 months old. Stable format mitigates the risk; falling back to a hand-rolled lxml EPUB walker is the named contingency.
7. **Catastrophic-scan handling.** Docling's OCR may fail completely on poor scans. `pdf-craft` is named as the documented external escape hatch for v3 onwards.
8. **The opt-in LLM assist.** Calls Anthropic SDK; needs an API key. Failure modes (rate-limit, network outage, no key set) must produce `provenance: "none"` rather than crash. Test in M4.

## 12. Acceptance against architecture.md

A direct cross-check against the architecture's acceptance criteria in §5:

| Architecture requirement | This spec |
|---|---|
| Discover chapter structure with enough confidence to drive a chapter-by-chapter ingest loop | `survey()` returns chapters[] with provenance + confidence; consumer reads `map.provenance` |
| Process any individual chapter into vault content without compensating for layout noise, page debris, ambiguous provenance | `extract_chapter()` returns `simple_view` with cleaned per-block text, page-anchored, with quality flags |
| Attach correct chapter and page locators to every note it creates | `chapters[].locator` (structured, not formatted) lets the skill render `cite_locator: "ch3, pp 142–145"` |
| Trust the tool to flag the cases where extraction quality is poor enough that ingestion should pause | Exit code 2 + `quality.flags` + `failed_region` blocks. Three regimes documented in §6.3 |
| Same tool serves every book shape without each shape becoming a separate code path the user has to choose between | Single CLI; `detect.py` chooses backend internally. Backend choice is visible in `quality.backend` for audit but not selectable |

---

*End of spec. Next step: invoke the `writing-plans` skill to produce the implementation plan for M1.*
