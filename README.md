# book-ingestion

A small Python library and CLI that turns a book file into a JSON intermediate representation an LLM workflow can read, quote, and cite.

`book-ingestion` is the *parsing* half of a two-tool split:

- **This tool** does the messy stuff: PDF parsing, layout analysis, chapter detection, per-block extraction, metadata mining, quality scoring, and printed-page-number recovery. It emits a typed JSON IR.
- **A downstream skill** reads that JSON, decides what to do with each chapter (or metadata blob), and authors content — without touching layout debris, OCR noise, regex-mining of imprint pages, or page-coordinate math.

The boundary is deliberate: the consumer never has to be a careful reader of prose. If a piece of text is unreliable, this tool *types* it as unreliable (`failed_region`, `confidence: POOR`, `flags: [...]`, `error: …`, `warnings: [...]`) so the consumer's job collapses to "check these fields", not "use judgment over prose."

## Why this exists

LLMs are good at understanding a chapter once you hand them clean text. They are *not* good at recovering from layout damage: running headers fused into paragraphs, table rows reflowed as prose, footnote markers attached to the wrong sentence, hyphenation-broken words mid-line, OCR errors that look like real words, ALL-CAPS title pages joined to author names, multiple ISBNs printed for the same edition, copyright dates spanning three publication events. If you let those reach the model, you get plausible-sounding nonsense — fine for a chat toy, catastrophic for citation-grade work.

The design principle is **honesty over completeness**:

- The tool extracts what it can and *refuses* what it can't, by emitting `failed_region` blocks (IR path) or setting `m.error` (metadata path) instead of guessing.
- Every IR extraction carries a categorical `confidence` (`EXCELLENT`/`GOOD`/`FAIR`/`POOR`) derived from the underlying parser's per-page scores.
- Document- and chapter-level `quality.flags` and metadata `warnings` surface known issues from a closed vocabulary, so consumers know to pause without having to infer trouble.
- Chapter maps carry an explicit `provenance` (`embedded` / `inferred` / `llm_assisted` / `none`).
- Printed page numbers are reconstructed (see [Printed page labels](#printed-page-labels)) so citations refer to "page 14" of the *book*, not "PDF page 18" of the file.
- ISBN-10 and ISBN-13 forms of the same edition collapse to one candidate; only genuine paperback-vs-hardback splits raise `MULTIPLE_ISBNS_DETECTED`.

If you're building anything where a hallucinated quote is a real cost — legal, academic, journalistic — that posture matters more than the speed of extraction.

## Status

| Milestone | Scope | State |
|---|---|---|
| **M1** | PDF MVP via Docling — IR + projection + CLI + cache + chapter map + quality | shipped |
| **M1.1** | Printed page labels (`/PageLabels` reader + heuristic inference) | shipped |
| **M2.0** | `extract_metadata` for PDF + EPUB — frontmatter-shaped, no Docling, sub-second | shipped |
| **M2.1** | Full EPUB IR backend (survey + extract_chapter for EPUB) | not started |
| **M3** | OCR fallback for scanned PDFs (Docling `do_ocr=True`) | not started |
| **M4** | Hardening, LLM-assisted structure, adversarial fixtures | not started |

## Two consumption profiles

The library serves two very different needs. Pick the install that matches yours.

| Profile | What you call | What you need installed |
|---|---|---|
| **Metadata only** — for "add this book to a reference manager" workflows. Sub-second per call. | `extract_metadata()` / `book-ingest metadata` | `pypdf` + `pydantic` + `typer` (~30 MB) |
| **Full IR** — for chapter-by-chapter ingestion into a vault, with layout cleanup and quality scoring. Multi-minute first run, cached thereafter. | `survey()` + `extract_chapter()` / `book-ingest survey` / `book-ingest extract` | Above + `docling` (~3 GB with PyTorch / transformers / accelerate) |

The metadata path is fully decoupled — importing `extract_metadata` does not pull Docling, and calling it does not invoke Docling. Try `survey` or `extract_chapter` without the `pdf-ir` extra installed and you get a clean `ImportError` pointing at the install command, not a library traceback.

## Install

Requires Python 3.11+.

### As a tool (`pipx install`, recommended)

For the metadata-only consumer (e.g. a downstream skill that shells out to `book-ingest metadata`):

```bash
git clone <this-repo>
cd book-ingestion
uv build
pipx install ./dist/book_ingestion-0.1.0-py3-none-any.whl
```

After that, `book-ingest` is on `$PATH` system-wide, isolated in pipx's own venv.

For the full IR consumer (`survey` / `extract_chapter`):

```bash
pipx install './dist/book_ingestion-0.1.0-py3-none-any.whl[pdf-ir]'
```

Or upgrade an existing metadata-only install:

```bash
pipx install --force './dist/book_ingestion-0.1.0-py3-none-any.whl[pdf-ir]'
```

Docling pulls a few hundred MB of ML model weights on first use; they are cached under `~/.cache/huggingface/`. Subsequent runs are much faster.

### As a library (`pip install`)

Same pattern, into your own Python environment:

```bash
pip install ./dist/book_ingestion-0.1.0-py3-none-any.whl              # metadata-only
pip install './dist/book_ingestion-0.1.0-py3-none-any.whl[pdf-ir]'    # with full IR
```

### For development

```bash
uv sync --extra dev      # everything: pypdf + docling + pytest + ruff + mypy + reportlab
```

## CLI

Four subcommands. JSON to stdout, errors to stderr, exit codes 0/1/2.

### `book-ingest metadata` — frontmatter extraction (light)

```bash
book-ingest metadata path/to/book.pdf > metadata.json
book-ingest metadata path/to/book.epub --pages 6
```

Returns a `BookMetadata` JSON: identifier (ISBN/DOI/arXiv), title/subtitle/full_title, creators (with role + first/last/raw), publisher, places, date / first_published, edition, language. Sub-second; no Docling.

The shell-out pattern with full exit-code branching (used by the `adding-references` skill):

```bash
err=$(mktemp -t book-ingest-err.XXXXXX) || exit 1
out=$(book-ingest metadata "$BOOK_PATH" 2>"$err")
case $? in
  0) # clean — consume $out as BookMetadata JSON
     ;;
  2) # extraction refused; m.error field set in $out — pause and surface to user
     ;;
  1) # hard error; $err contains structured {"error": "...", "type": "..."} JSON
     ;;
esac
rm -f "$err"
```

### `book-ingest survey` — chapter map (heavy, requires `[pdf-ir]`)

```bash
book-ingest survey path/to/book.pdf > survey.json
```

Parses the PDF once via Docling, builds a chapter map from the embedded outline (or infers one from typographic hints), and returns a `BookSurvey` describing the structure.

For a 232-page non-fiction title on an M-series MacBook, expect roughly 3–4 minutes the first time (Docling parse + model warmup), sub-second on subsequent runs (content-hash cache).

### `book-ingest extract` — one chapter (heavy, requires `[pdf-ir]`)

```bash
book-ingest extract path/to/book.pdf --chapter 3 > chapter-03.json
```

Returns a `ChapterContent` with a flat list of typed blocks (`paragraph`, `heading`, `table`, `figure_caption`, `footnote`, `page_break`, `failed_region`) in reading order, each with a `page` (PDF page) and a `page_label` (printed page) when known.

### `book-ingest cache` — content-hash-keyed cache

```bash
book-ingest cache list
book-ingest cache clear path/to/book.pdf
book-ingest cache clear --all
```

Cache is keyed by the SHA-256 of the file content, so moving a book on disk doesn't invalidate it. Schema-version mismatch invalidates entries transparently.

### Exit codes

- `0` — success, JSON usable.
- `2` — extraction refused (metadata: `m.error is not None`; survey/extract: `map.provenance == "none"` or all blocks are `failed_region`). JSON still emitted on stdout. Caller should pause.
- `1` — hard error (file not found, unsupported format, missing optional dep). Structured error JSON on stderr; no payload on stdout.

### Other flags

- `--cache-dir <PATH>` — override `~/.cache/book-ingestion/`
- `--no-cache` — force re-parse (writes still update the cache)
- `--quiet` / `--verbose` — adjust log level on stderr
- `--json-schema {survey,extract}` — emit the JSON schema for the IR shape (useful for prompt construction)

## Library API

Three public functions, deterministic given the same input and cache state.

```python
from book_ingestion import extract_metadata, survey, extract_chapter
from book_ingestion import BookMetadata, BookSurvey, ChapterContent
```

### `extract_metadata(path, *, pages=6) -> BookMetadata`

Light, sub-second. No Docling. Returns a typed `BookMetadata`; the caller decides on `error` and `warnings`.

```python
m = extract_metadata("path/to/book.epub")

if m.error is not None:
    # encrypted / DRM / malformed — pause or route to alternative
    ...
elif m.warnings:
    # heuristic / partial extraction — data usable, inspect codes
    ...
else:
    # clean
    print(m.identifier.value, m.full_title)
    for c in m.creators:
        print(c.role.value, c.first_name, c.last_name)

m.model_dump(mode="json")   # the dict shape consumers like
```

### `survey(path) -> BookSurvey` and `extract_chapter(path, idx) -> ChapterContent`

Heavy, Docling-backed. Requires the `[pdf-ir]` extra.

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

If Docling isn't installed, both functions raise a clear `ImportError` pointing at the install command — not a library traceback.

## The IR in samples

### `BookMetadata` (returned by `extract_metadata`)

```jsonc
{
  "schema_version": "1.1",
  "kind": "book_metadata",
  "identifier": {
    "kind": "isbn",
    "value": "9780520295711",
    "candidates": [
      { "kind": "isbn", "value": "9780520295711", "edition_hint": "paperback" },
      { "kind": "isbn", "value": "9780520968431", "edition_hint": "ebook" }
    ]
  },
  "title": "Gaza",
  "subtitle": "An Inquest Into Its Martyrdom",
  "full_title": "Gaza: An Inquest Into Its Martyrdom",
  "creators": [
    {
      "role": "author",
      "first_name": "Norman",
      "last_name": "Finkelstein",
      "raw": "Finkelstein, Norman; "
    }
  ],
  "publisher": "University of California Press",
  "places": ["Berkeley"],
  "date": "2018",
  "first_published": null,
  "edition": null,
  "language": "en",
  "error": null,
  "warnings": [
    { "code": "language_normalised",            "detail": "en-US -> en" },
    { "code": "dc_creator_trailing_punctuation","detail": "creator 'Finkelstein, Norman; ' had trailing ; or ," },
    { "code": "subtitle_not_in_opf",            "detail": "subtitle from title-page xhtml: An Inquest Into Its Martyrdom" }
  ]
}
```

#### Warning vocabulary

`m.warnings` is a list of `MetadataWarning(code, detail)` entries drawn from a closed set. The **material** column reflects the convention the `adding-references` skill uses for its Step 6 confirmation trigger: anything material asks the user to pause and check; informational entries don't.

| Code | Fires when | Material? |
|---|---|---|
| `incomplete_extraction` | Joint-emptiness on publisher AND places AND dates — extractor likely missed the imprint page. Or a recoverable library exception during parsing. | material |
| `no_text_extracted` | PDF has no embedded text (scanned without OCR). All other fields will be at defaults. | material |
| `multiple_isbns_detected` | More than one distinct ISBN edition remains after ISBN-10/13 dedupe (i.e., a real paperback-vs-hardback split). | material |
| `multiple_places_detected` | More than one publication place detected on the imprint page. | material |
| `subtitle_not_in_opf` | EPUB only: subtitle was synthesised from the title-page xhtml rather than `<dc:title>`. | material |
| `title_all_caps_in_source` | Raw title text is ALL-CAPS in the source. No auto-casing applied. | informational |
| `dc_creator_trailing_punctuation` | EPUB only: trailing `;` or `,` was stripped from the `<dc:creator>` text. | informational |
| `language_normalised` | EPUB only: BCP-47 tag stripped to primary subtag (`"en-US"` → `"en"`). | informational |

The hard-failure codes that go in `m.error` (not `m.warnings`) are `encrypted`, `drm_protected`, `malformed_pdf`, `malformed_epub`. When `error` is set, the other fields are at defaults.

### `BookSurvey` (returned by `survey`)

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
  "metadata": { "title": "...", "authors": [], "publisher": null, ... },
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

### `ChapterContent` (returned by `extract_chapter`)

```jsonc
{
  "schema_version": "1.1",
  "kind": "chapter_content",
  "source": { ... },
  "chapter": { "index": 8, "title": "...", "locator": { ... } },
  "simple_view": [
    { "type": "heading",   "level": 1, "text": "Chapter One", "page": 14, "page_label": null, "confidence": "EXCELLENT" },
    { "type": "paragraph", "text": "The relationship of the Jews with...", "page": 14, "page_label": null, "confidence": "EXCELLENT", "footnote_refs": [] },
    { "type": "page_break", "page": 15, "page_label": "11" },
    { "type": "paragraph", "text": "...", "page": 15, "page_label": "11", "confidence": "EXCELLENT" }
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
2. **Heuristic inference from running headers/footers.** Scan the first/last short text on each PDF page for an arabic numeral. Compute `offset = printed_page - pdf_page` for every candidate, take the dominant offset by majority, and apply it to every PDF page within the observed range. This handles books that lack `/PageLabels` and tolerates chapter-cover pages with no page number.

Both paths set `page_label_provenance` on the `BookSurvey` to `embedded` / `inferred` / `none`. Every block in a `ChapterContent` carries `page_label: str | None` — `None` whenever neither path produced a label for that PDF page.

A worked example on the `What is Modern Israel` test fixture (232 pages, no `/PageLabels`): inference covers 218 of 232 pages. The 14 unlabelled pages are front matter where applying the dominant offset would yield non-positive labels.

## What this tool does *not* do

- Author vault content, summaries, or annotations. That's the consumer's job.
- Fetch books. Files are paths on disk; you supply them.
- Reconcile metadata against Zotero, Calibre, or any external store. (Network lookup belongs in `zotero-mcp`'s `lookup_*` tools.)
- Hold state between invocations beyond the content-hash cache.
- Make LLM calls in default operation. The opt-in `--llm-assist` for chapter-structure inference is M4.
- Strip running headers and page-number debris from `simple_view`. Those appear as their own paragraph blocks; consumers strip them. (A future M4 quality flag may help.)
- Auto title-case ALL-CAPS strings (corrupts iPhone / DNA / USA — consumers decide, we just flag `TITLE_ALL_CAPS_IN_SOURCE`).

## Known heuristic gaps

These are real shapes the extractor handles imperfectly. Each has a known reason and a narrow fix-path. The discipline is **fixture-as-it-arises** — we don't pre-emptively patch (over-fitting guesses produces brittle code); we wait for a real-world fixture to surface the case, then harden narrowly + add a synthetic regression test that pins it.

The safety net for all of these is the `incomplete_extraction` warning, which fires when the imprint-mining produces nothing on any field. Consumers should treat that warning as a "pause and confirm" signal — silent failures should not happen even when an individual heuristic misses.

- **Publisher keyword list is narrow.** Presses not in the small built-in set (Verso, Penguin, Routledge, Press, Books, Publishing) silently produce `publisher=null`. The `\b\w+ University Press\b` regex catches most academic publishers; unconventional names (Suhrkamp, Gallimard, Haymarket, OR Books, …) need to be added as they arise.
- **Place-name list is narrow.** Cities not in the small hardcoded list (London, New York, Cambridge, Oxford, Boston, Chicago, …) silently produce empty `places`. The list grows fixture-by-fixture.
- **Edition phrase loses ordinal abbreviations.** `"Second updated edition"` matches cleanly, but `"updated 2nd ed."` falls outside the regex vocabulary (the keyword set is currently `First|Second|Third|Fourth|Fifth|Revised|Updated|Paperback|Hardback`).
- **Mixed-case PDF title without `/Info /Title`.** Falls back to a heuristic that takes the first non-trivial line on page 1. Works for typical layouts but may misfire on pages with banners, dedications, or epigraphs above the title.
- **ALL-CAPS title-block boundary uses a 15-char threshold.** Two consecutive ALL-CAPS lines ≥15 chars are treated as title + subtitle; shorter pairs are joined as one continued title. A short single-word ALL-CAPS subtitle could fold into the title block.
- **Adversarial EPUB shapes** — unusual OPF locations, deeply nested OEBPS, multi-creator strings beyond `"Smith, J. and Jones, K."`. Handled case-by-case as they appear.

## Project layout

```
book-ingestion/
  src/book_ingestion/
    __init__.py             # exports survey, extract_chapter, extract_metadata,
                            #         BookSurvey, ChapterContent, BookMetadata
    api.py                  # public dispatch + lazy backend registry
    ir.py                   # Pydantic v2 IR models; SCHEMA_VERSION
    metadata.py             # M2.0 — BookMetadata + sub-models + ISBN/edition helpers
    cli.py                  # Typer app (survey, extract, metadata, cache)
    cache.py                # content-hash-keyed disk cache
    detect.py               # format/backend sniffing
    page_labels.py          # /PageLabels reader + heuristic inference
    py.typed                # PEP 561 marker
    backends/               # heavy IR path (Docling)
      base.py               # Backend Protocol + Context
      pdf_docling.py        # v1 PDF backend; docling lazy-imported
    extractors/             # M2.0 lightweight metadata path
      base.py               # MetadataExtractor Protocol
      pdf.py                # PdfMetadataExtractor — pypdf
      epub.py               # EpubMetadataExtractor — stdlib zipfile + xml.etree
    projection/
      to_simple_view.py     # DoclingDocument → typed block list
    structure/
      embedded_toc.py       # chapter map from heading hints
    quality/
      flags.py              # closed vocabulary of quality flags
      scoring.py            # numeric → categorical confidence
  tests/
    fixtures/               # synthetic PDF + EPUB builders
    test_metadata_*.py      # M2.0 fast unit + synthetic-fixture coverage
    test_metadata_real.py   # @slow @real_book — Holocaust Industry, Gaza
    test_*.py               # M1 / M1.1 IR coverage
    test_import_isolation.py # subprocess test verifying metadata path stays Docling-free
  docs/
    superpowers/            # design specs + implementation plans
  test/                     # the real-book fixture (gitignored)
  acceptance/               # local-only end-to-end output (gitignored)
  .cowork/                  # per-developer cross-agent messaging (gitignored)
```

## Develop

```bash
uv sync --extra dev                 # full dev env including docling
uv run pytest -m "not slow"         # fast unit + synthetic suites, sub-second
uv run pytest -m "slow and real_book"  # real-book acceptance (needs files in test/)
uv run ruff check src tests
uv run mypy
```

The slow suite is marked `@pytest.mark.slow` and split further by `@pytest.mark.real_book` for tests that depend on files under `test/`. Routine CI should run `not slow` per commit and the full suite nightly.

After packaging changes, regenerate and reinstall the wheel:

```bash
uv build
pipx install --force ./dist/book_ingestion-0.1.0-py3-none-any.whl              # metadata-only
pipx install --force './dist/book_ingestion-0.1.0-py3-none-any.whl[pdf-ir]'    # with docling
```

## License

MIT, matching Docling, EbookLib, and the rest of the open-source PDF ecosystem.

## See also

- [`architecture.md`](architecture.md) — statement of intent, what's in and out of scope
- [`docs/superpowers/specs/2026-05-12-book-ingestion-design.md`](docs/superpowers/specs/2026-05-12-book-ingestion-design.md) — M1 design specification
- [`docs/superpowers/specs/2026-05-13-extract-metadata-design.md`](docs/superpowers/specs/2026-05-13-extract-metadata-design.md) — M2.0 metadata design specification
- [`docs/superpowers/plans/2026-05-12-book-ingestion-m1.md`](docs/superpowers/plans/2026-05-12-book-ingestion-m1.md) — M1 implementation plan
- [`docs/superpowers/plans/2026-05-12-book-ingestion-m1.1.md`](docs/superpowers/plans/2026-05-12-book-ingestion-m1.1.md) — M1.1 printed-labels plan
- [`docs/superpowers/plans/2026-05-13-extract-metadata-m2.0.md`](docs/superpowers/plans/2026-05-13-extract-metadata-m2.0.md) — M2.0 implementation plan
