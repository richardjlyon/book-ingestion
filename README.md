# book-ingestion

A small Python library and CLI that turns a book file into a JSON intermediate representation an LLM workflow can read, quote, and cite.

`book-ingestion` is the *parsing* half of a two-tool split:

- **This tool** does the messy stuff: PDF parsing, layout analysis, chapter detection, per-block extraction, quality scoring, and printed-page-number recovery. It emits a typed JSON IR.
- **A downstream skill** reads that JSON, decides what to do with each chapter, and authors vault content — without touching layout debris, OCR noise, or page-coordinate math.

The boundary is deliberate: the skill never has to be a careful reader of prose. If a piece of text is unreliable, this tool *types* it as unreliable (`failed_region`, `confidence: POOR`, `flags: [...]`) so the consumer's job collapses to "check these fields", not "use judgment over prose."

## Why this exists

LLMs are good at understanding a chapter once you hand them clean text. They are *not* good at recovering from layout damage: running headers fused into paragraphs, table rows reflowed as prose, footnote markers attached to the wrong sentence, hyphenation-broken words mid-line, OCR errors that look like real words. If you let those reach the model, you get plausible-sounding nonsense — fine for a chat toy, catastrophic for citation-grade work.

The design principle is **honesty over completeness**:

- The tool extracts what it can and *refuses* what it can't, by emitting `failed_region` blocks instead of guessing.
- Every extraction carries a categorical `confidence` (`EXCELLENT`/`GOOD`/`FAIR`/`POOR`) derived from the underlying parser's per-page scores.
- Document- and chapter-level `quality.flags` surface known issues from a closed vocabulary, so consumers know to pause without having to infer trouble.
- Chapter maps carry an explicit `provenance` (`embedded` / `inferred` / `llm_assisted` / `none`) so the consumer knows how much to trust the structural partition.
- Printed page numbers are reconstructed (see [Printed page labels](#printed-page-labels)) so citations refer to "page 14" of the *book*, not "PDF page 18" of the file.

If you're building anything where a hallucinated quote is a real cost — legal, academic, journalistic — that posture matters more than the speed of extraction.

## Status

| Milestone | Scope | State |
|---|---|---|
| **M1** | PDF MVP via Docling — IR + projection + CLI + cache + chapter map + quality | shipped |
| **M1.1** | Printed page labels (via `/PageLabels` reader + heuristic inference) | shipped |
| **M2** | EPUB backend (EbookLib + lxml) | not started |
| **M3** | OCR fallback for scanned PDFs (Docling `do_ocr=True`) | not started |
| **M4** | Hardening, LLM-assisted structure, adversarial fixtures | not started |

## Install

Requires Python 3.11+.

```bash
uv sync --extra dev
```

The runtime dependencies are `docling`, `pydantic`, `typer`, and `pypdf`. The dev extra adds `pytest`, `syrupy`, `ruff`, `mypy`, and `reportlab` (used to build deterministic PDF fixtures).

Docling pulls a few hundred MB of ML model weights on first use; they are cached under `~/.cache/huggingface/` by default. Subsequent runs are much faster.

## CLI

### Survey a book

`survey` is fast and metadata-only: it parses the PDF once, builds a chapter map from the embedded outline (or infers one if absent), and returns a `BookSurvey` describing the structure.

```bash
uv run book-ingest survey path/to/book.pdf > survey.json
```

For a 232-page non-fiction title on a M-series MacBook, expect roughly 3–4 minutes the first time (Docling parse + model warmup), sub-second on subsequent runs (content-hash cache).

### Extract one chapter

```bash
uv run book-ingest extract path/to/book.pdf --chapter 3 > chapter-03.json
```

Returns a `ChapterContent` with a flat list of typed blocks (`paragraph`, `heading`, `table`, `figure_caption`, `footnote`, `page_break`, `failed_region`) in reading order, each with a `page` (PDF page) and a `page_label` (printed page) when known.

### Cache management

```bash
uv run book-ingest cache list
uv run book-ingest cache clear path/to/book.pdf
uv run book-ingest cache clear --all
```

Cache is keyed by the SHA-256 of the *file content*, so moving a book on disk doesn't invalidate it. A schema-version mismatch invalidates entries transparently.

### Exit codes

- `0` — success, JSON usable
- `2` — extraction refused (e.g. no chapters detectable; JSON still emitted with `map.provenance: "none"` and quality flags). The consumer should pause.
- `1` — hard error (file not found, unsupported format, unhandled exception). Error JSON on stderr; no payload on stdout.

### Other flags

- `--cache-dir <PATH>` — override `~/.cache/book-ingestion/`
- `--no-cache` — force re-parse (writes still update the cache)
- `--quiet` / `--verbose` — adjust log level on stderr
- `--json-schema {survey,extract}` — emit the JSON schema for the IR shape (useful for prompt construction)

## Library API

```python
from book_ingestion import survey, extract_chapter

s = survey("path/to/book.pdf")
print(s.map.provenance, len(s.chapters))

for chapter in s.chapters:
    c = extract_chapter("path/to/book.pdf", chapter.index)
    for block in c.simple_view:
        if block.type == "paragraph":
            cite = f"{c.chapter.title}, p.{block.page_label or '?'}"
            print(cite, "—", block.text[:80])
```

Both functions are deterministic given the same input and cache state.

## The IR in one sample

```jsonc
{
  "schema_version": "1.1",
  "kind": "book_survey",
  "source": {
    "path": "/abs/path/to/book.pdf",
    "sha256": "ab12…",
    "size_bytes": 4823104,
    "format": "pdf"
  },
  "metadata": { "title": "...", "authors": ["..."], "language": "en", ... },
  "chapters": [
    {
      "index": 0,
      "title": "Introduction",
      "locator": {
        "kind": "page_range",
        "start_page": 14, "end_page": 22,                // PDF page indices
        "start_page_label": "10", "end_page_label": "18" // printed page numbers
      },
      "provenance": "embedded",
      "confidence": "EXCELLENT"
    }
    // ... more chapters
  ],
  "map":     { "provenance": "embedded", "confidence": "GOOD", "method": "pdf_outline" },
  "quality": { "backend": "docling_pdf", "pages_total": 232, "flags": ["embedded_toc_present", "page_labels_inferred"] },
  "page_labels": { "15": "11", "16": "12", "17": "13", "...": "..." },
  "page_label_provenance": "inferred",
  "cache_paths": { "docling_document": "/Users/.../sha256/docling.json" }
}
```

A `ChapterContent` looks similar but its `simple_view` is the list of typed blocks for one chapter:

```jsonc
{
  "schema_version": "1.1",
  "kind": "chapter_content",
  "source": { ... },
  "chapter": { "index": 8, "title": "...", "locator": { ... } },
  "simple_view": [
    { "type": "heading", "level": 1, "text": "Chapter One", "page": 14, "page_label": null, "confidence": "EXCELLENT" },
    { "type": "paragraph", "text": "The relationship of the Jews with...", "page": 14, "page_label": null, "confidence": "EXCELLENT", "footnote_refs": [] },
    { "type": "page_break", "page": 15, "page_label": "11" },
    { "type": "paragraph", "text": "...", "page": 15, "page_label": "11", "confidence": "EXCELLENT" },
    // ... and so on
  ],
  "quality": {
    "backend": "docling_pdf",
    "pages_processed": [14, 15, 16, 17, 18, 19, 20, 21, 22],
    "block_confidence_counts": { "EXCELLENT": 57, "GOOD": 6, "FAIR": 2 },
    "flags": []
  },
  "cache_paths": { "docling_chapter": "/Users/.../sha256/chapter-8.docling.json" }
}
```

## Printed page labels

Citations against PDF page indices ("PDF page 18") are not what humans cite. The book printed on page 14 needs to come back as `"page 14"`. Two recovery paths, in order:

1. **Read `/PageLabels` directly via pypdf.** Many publishers set this dictionary correctly (Roman numerals for front matter, Arabic for body, sometimes a separate sequence for appendices). When present, labels are exact and per-page.
2. **Heuristic inference from running headers/footers.** Scan the first/last short text on each PDF page for an arabic numeral. Compute `offset = printed_page - pdf_page` for every candidate, take the dominant offset by majority, and apply it to every PDF page within the observed range. This handles books that lack `/PageLabels` and tolerates chapter-cover pages with no page number (the offset fills the gap).

Both paths set `page_label_provenance` on the `BookSurvey` to `embedded` / `inferred` / `none`. Every block in a `ChapterContent` carries `page_label: str | None` — `None` whenever neither path produced a label for that PDF page.

A worked example on the test fixture (`What is Modern Israel`, 232 pages, no `/PageLabels`): inference covers 218 of 232 pages. The 14 unlabelled pages are front matter where applying the dominant offset would yield non-positive labels. The chapter-one closing sentence (printed page 14 of the book) is recoverable as the `paragraph` block on PDF page 18 with `page_label: "14"`.

## What this tool does *not* do

- Author vault content, summaries, or annotations. That's the consumer skill's job.
- Fetch books. Files are paths on disk; you supply them.
- Reconcile metadata against Zotero, Calibre, or any external store.
- Hold state between invocations beyond the content-hash cache.
- Make LLM calls in default operation. The opt-in `--llm-assist` for chapter-structure inference is M4.
- Strip running headers and page-number debris from `simple_view`. Those appear as their own paragraph blocks; consumers strip them. (A future M4 quality flag may help.)

## Project layout

```
book-ingestion/
  src/book_ingestion/
    __init__.py        # exports survey, extract_chapter, BookSurvey, ChapterContent
    api.py             # public dispatch + backend registry
    ir.py              # Pydantic v2 models; SCHEMA_VERSION
    cli.py             # Typer app
    cache.py           # content-hash-keyed disk cache
    detect.py          # format/backend sniffing
    page_labels.py     # /PageLabels reader + heuristic inference
    backends/
      base.py          # Backend Protocol + Context
      pdf_docling.py   # v1 PDF backend
    projection/
      to_simple_view.py  # DoclingDocument → typed block list
    structure/
      embedded_toc.py  # chapter map from heading hints
    quality/
      flags.py         # closed vocabulary of quality flags
      scoring.py       # numeric → categorical confidence
  tests/               # unit + slow integration + real-book acceptance
  docs/                # design spec + implementation plans
  test/                # the real-book fixture (gitignored)
  acceptance/          # local-only end-to-end output (gitignored)
```

## Develop

```bash
uv run pytest -m "not slow"      # fast unit tests, < 1 s
uv run pytest -m slow             # Docling + real-book integration tests, several minutes
uv run ruff check src tests
uv run mypy
```

The slow suite is marked `@pytest.mark.slow` and split further by `@pytest.mark.real_book` for tests that depend on the file in `test/`. Routine CI should run `not slow` per commit and the full suite nightly.

## License

MIT, matching Docling, EbookLib, and the rest of the open-source PDF ecosystem.

## See also

- `architecture.md` — statement of intent, what's in and out of scope
- `docs/superpowers/specs/2026-05-12-book-ingestion-design.md` — design specification
- `docs/superpowers/plans/2026-05-12-book-ingestion-m1.md` — M1 implementation plan
- `docs/superpowers/plans/2026-05-12-book-ingestion-m1.1.md` — M1.1 printed-labels plan
