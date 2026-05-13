# `extract_metadata` — design specification (M2.0)

**Status:** draft 1, 2026-05-13
**Author:** Richard Lyon, with Claude (brainstorming pass)
**Driver:** sister skill `adding-references` (Zotero ingestion). Spec from skill side: `~/Resilio/claude-cowork/project/memory-system/book-pdf-metadata.spec.md`.
**Cross-agent thread:** `.cowork/archive/0001-…`, `.cowork/archive/0002-…`, `.cowork/archive/0003-…`, `.cowork/inbox/0004-…`.
**Output:** this document (design); implementation plan to follow via the `writing-plans` skill.

---

## 1. Scope

`extract_metadata` is a new public function in `book_ingestion` that returns frontmatter-shaped metadata for a book file (PDF or EPUB) in under a second. It is designed for the `adding-references` skill's Zotero-add path, which is latency-sensitive and blocks user interaction.

**In scope (M2.0).**

- New public function `extract_metadata(path, *, pages=6) -> BookMetadata`.
- New `MetadataExtractor` Protocol with two implementations: `PdfMetadataExtractor` (pypdf) and `EpubMetadataExtractor` (stdlib `zipfile` + `xml.etree.ElementTree`).
- New `BookMetadata` Pydantic model and sub-models in `src/book_ingestion/metadata.py`.
- Closed-vocabulary enums for `IdentifierKind`, `EditionHint`, `CreatorRole`, `ErrorCode`, `WarningCode`.
- Three-layer test coverage: fast unit, synthetic-fixture integration, real-fixture acceptance.

**Zero new runtime dependencies.** pypdf is already in the runtime set (used by `page_labels.py`); the EPUB path uses only stdlib (`zipfile`, `xml.etree.ElementTree`). `reportlab` is already in the dev extra (used by existing PDF fixture helpers).

**Out of scope (deferred to M2.1).**

- The full EPUB backend (Docling-style survey + chapter extraction for EPUB).
- Any `BookSurvey.metadata` adoption of `BookMetadata` (schema version stays `1.1`).
- Multi-edition-ISBN PDFs (we don't have a fixture for the paperback-vs-hardback heuristic — defer to fixtures-as-they-arise).
- LLM-assisted metadata recovery.
- HTTP lookup, retry, or alternate-form resolution (owned by `zotero-mcp` per `~/Resilio/claude-cowork/project/memory-system/zotero-lookup-resilience.spec.md`).

**Out of scope (general).**

- Mobi / azw3 / other formats (future).
- Auto title-casing of ALL-CAPS strings (deliberately rejected — corrupts iPhone / DNA / USA; downstream's job).
- A `primary_place` field (deliberately rejected — caller picks `places[0]`).
- Caching (the operation is sub-second; caching adds invalidation surface for no benefit).

## 2. Architecture

```
              ┌─────────────────────────────────────────────────┐
              │                     api.py                      │
              │   extract_metadata(path, *, pages=6)            │
              └────────────────────────┬────────────────────────┘
                                       │
                            detect.detect_format(path)
                                       │
                  ┌────────────────────┴────────────────────┐
                  ▼                                         ▼
        ┌───────────────────┐                    ┌────────────────────┐
        │ extractors/pdf.py │                    │ extractors/epub.py │
        │ pypdf             │                    │ zipfile + xml.etree│
        └────────┬──────────┘                    └─────────┬──────────┘
                 │                                         │
                 └──────────────► BookMetadata ◄───────────┘
                                       │
                                       ▼
                              caller (adding-references)
```

**No Docling on this path.** Both extractors complete in well under a second on typical books.

**No shared `Context` with backends.** `backends/base.py:Context` carries `cache` / `use_cache` / `llm_assist`; extractors use none of those. `extractors/base.py` defines `MetadataExtractor` only — no context object.

**No caching.** `extract_metadata` does not consult or populate the on-disk cache. The function signature stays honest: `extract_metadata(path, *, pages=6)`.

### Module layout

```
src/book_ingestion/
  __init__.py            # re-export extract_metadata, BookMetadata
  api.py                 # adds extract_metadata + _EXTRACTORS registry
  metadata.py            # NEW — BookMetadata + sub-models + enums
  extractors/            # NEW
    __init__.py
    base.py              # MetadataExtractor Protocol
    pdf.py               # PdfMetadataExtractor — pypdf
    epub.py              # EpubMetadataExtractor — stdlib
```

Naming: `pdf.py` / `epub.py` (not `pdf_pypdf.py` / `epub_opf.py`). Unlike backends — where parser tech varies per format and may multiply (Docling now, OCR later) — metadata extractors are unlikely to have alternative implementations per format.

## 3. Public API

```python
def extract_metadata(path: Path, *, pages: int = 6) -> BookMetadata: ...
```

- `path` — absolute path to a `.pdf` or `.epub` file. Format detected via `detect.detect_format()`.
- `pages` — PDF only: how many leading pages to scan for text. EPUB ignores this. Default 6, matching the skill spec.
- Returns: always a `BookMetadata`. **Never raises on file-shape failures.** Hard failures (encryption, DRM, malformed) surface as `error` field; partial failures as `warnings`.
- Raises: `FileNotFoundError`, `ValueError` from `detect_format` for programmer errors only (file missing, unsupported extension, magic-bytes mismatch).

### Caller contract

```python
m = extract_metadata("book.epub")
if m.error is not None:
    # hard failure: other fields at defaults; pause or route to alternative
    ...
elif m.warnings:
    # partial / heuristic extraction; data is usable, inspect warnings
    ...
else:
    # clean extraction
    ...
```

`m.model_dump(mode="json")` produces the dict shape described in the skill's spec.

## 4. Data model

In `src/book_ingestion/metadata.py`. Sub-models marked `frozen=True` matching the rest of `ir.py`.

### 4.1 Closed vocabularies

```python
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

### 4.2 Sub-models

```python
class IdentifierCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: IdentifierKind
    value: str                                    # canonical (digits-only for ISBN)
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
    raw: str | None = None                        # original string from source


class MetadataWarning(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: WarningCode
    detail: str | None = None
```

### 4.3 Top-level `BookMetadata`

```python
class BookMetadata(BaseModel):
    schema_version: str = SCHEMA_VERSION          # reuses ir.SCHEMA_VERSION
    kind: Literal["book_metadata"] = "book_metadata"

    # Identifier
    identifier: Identifier = Field(default_factory=Identifier)

    # Title
    title: str | None = None                      # raw, whitespace-normalised, NOT title-cased
    subtitle: str | None = None
    full_title: str | None = None                 # composed by extractor: f"{title}: {subtitle}"

    # Authorship
    creators: list[Creator] = Field(default_factory=list)

    # Publication
    publisher: str | None = None
    places: list[str] = Field(default_factory=list)   # ordered as printed; no primary_place
    date: str | None = None                       # most-useful (this-edition copyright)
    first_published: str | None = None
    edition: str | None = None

    # Other
    language: str | None = None                   # normalised: "en" not "en-US"

    # Diagnostics
    error: ErrorCode | None = None
    warnings: list[MetadataWarning] = Field(default_factory=list)
```

**Design notes.**

- `full_title` is *stored*, not computed. The extractor composes it from `title + ": " + subtitle` when both present, else `full_title == title`. Saves callers from re-composing.
- No top-level `translator` field. Translators live in `creators` with `role=TRANSLATOR`. Single source of truth.
- No `source` block (path / sha256 / size). Computing sha256 over a multi-MB file defeats "fast metadata"; caller knows the path.
- `error` and `warnings` co-exist. `error` set → unrecoverable; other fields at defaults. `warnings` non-empty without `error` → partial / heuristic, data usable.

## 5. PDF extractor (`PdfMetadataExtractor`)

### 5.1 Pipeline

```
PDF path
  ├─► pypdf.PdfReader; reader.is_encrypted? → BookMetadata(error=ENCRYPTED) [stop]
  ├─► reader.metadata (/Info) — title/author/creator (hints; often wrong)
  ├─► reader.pages[0..pages-1].extract_text(); all empty? → BookMetadata(warnings=[NO_TEXT_EXTRACTED]) [stop]
  ├─► IDENTIFIERS: regex pass for DOI / arXiv / ISBN → Identifier + candidates
  ├─► TITLE/SUBTITLE: page-1 mining + /Info fallback → title, subtitle, full_title
  ├─► CREATORS: author-block parsing → list[Creator]
  ├─► PUBLISHER / PLACES / DATE / EDITION: imprint block on pages 2..pages
  ├─► LANGUAGE: default "en"
  └─► WARNINGS aggregated → BookMetadata
```

Exceptions raised inside pypdf (e.g. `PdfReadError` on corruption) are caught at the extractor boundary and translated to `BookMetadata(error=MALFORMED_PDF, warnings=[INCOMPLETE_EXTRACTION (detail=str(e))])`.

### 5.2 Identifier extraction

- **DOI** — pattern `10\.\d{4,9}/[-._;()/:A-Z0-9]+` (case-insensitive). First match wins.
- **arXiv** — patterns `arXiv:\s*\d{4}\.\d{4,5}` and `arxiv\.org/abs/\d{4}\.\d{4,5}` (case-insensitive). First match wins.
- **ISBN** — patterns `ISBN[ -]*(97[89][- 0-9]{10,})` and `ISBN[ -]*([0-9][- 0-9]{8,10}[0-9X])` (case-insensitive). All matches collected; canonicalize by stripping separators (digits-only; final `X` allowed for ISBN-10).
- **Multi-ISBN classification.** For each ISBN match, look in a ~80-char window for edition-hint keywords: paperback / pbk / softcover / trade paperback → `PAPERBACK`; hardback / hardcover / hb / cloth → `HARDBACK`; pdf / ebook / kindle / epub / digital → `EBOOK`. No match → `UNSPECIFIED`.
- **ISBN-10 / ISBN-13 equivalence dedupe.** After canonicalization, compute the ISBN-13 form of any ISBN-10 (prefix `"978"` + first 9 digits + recomputed check digit) and treat the pair as one candidate. Holocaust Industry prints both `"1-84467-487-8"` (ISBN-10) and `"978-1-84467-487-9"` (ISBN-13) for the same paperback; they collapse to one. The edition hint of the ISBN-13 form (when both forms carry one) wins on conflict.
- **Priority for `identifier.value`.** First `PAPERBACK`, else first `HARDBACK`, else first `UNSPECIFIED`, else first `EBOOK`. All deduped candidates go into `candidates`. Flag `MULTIPLE_ISBNS_DETECTED` only when the **deduped** set has more than one entry — i.e., a paperback-vs-hardback or print-vs-ebook split, not the ISBN-10 / ISBN-13 same-edition pair.

No `isbnlib` dependency. Canonicalization is a one-liner; validation is upstream's problem.

### 5.3 Title / subtitle

Two-stage approach:

1. **`/Info /Title`** is the primary source when it is non-empty and not equal to `path.stem`. (Many PDF generators set `/Title` to the filename automatically; we treat that as no signal.)
2. **Page-1 text mining** otherwise. Two sub-paths, tried in order:
   - **ALL-CAPS block.** First block of ALL-CAPS lines without trailing punctuation on page 1. Join adjacent ALL-CAPS lines with single spaces. Stop at blank line, author signal (line containing " by "), or transition to non-CAPS. Subtitle = the next ALL-CAPS block on page 1 before the author block.
   - **First non-trivial line.** If no ALL-CAPS block is present, take the first non-empty line on page 1 with at least 5 characters that does not match a header/footer pattern (page number, single short string repeated across pages). Subtitle = the next non-empty line if shorter than the title line. This path is heuristic and may misfire on layouts with banners or quotes above the title.

Compose `full_title = f"{title}: {subtitle}"` when both present; else `full_title = title`.

Flag `TITLE_ALL_CAPS_IN_SOURCE` whenever the raw title string is ALL-CAPS, regardless of which path produced it. **No auto title-casing.**

The Holocaust Industry fixture (three-line ALL-CAPS title with subtitle) is the M2.0 acceptance case for the ALL-CAPS path. The mixed-case fallback is heuristic and untested by a real fixture — flagged in §9 as a hardening target.

### 5.4 Creators

Author-block parsing follows the title/subtitle block, before the imprint. Patterns:

- `by Author Name` — single creator.
- `Author Name` alone on a line — single creator.
- `Author1 and Author2`, `Author1, Author2` — multiple creators (split on `, ` and ` and `).
- Role prefixes: `translated by` → `TRANSLATOR`; `edited by` → `EDITOR`; `with foreword by` → `FOREWORD`.

Name parsing:

- `"Norman G. Finkelstein"` — split on last whitespace; `last_name = "Finkelstein"`, `first_name = "Norman G."`.
- `"Finkelstein, Norman G."` — comma-form; `last_name = "Finkelstein"`, `first_name = "Norman G."`.
- Single token — `last_name` only, `first_name = None`.
- `raw` always populated with the original substring (post-whitespace-normalisation, pre-name-parsing).
- **Source order preserved.** Multiple creators are returned in the order they appear in the source text. No alphabetical or otherwise re-ordering — citation order is meaningful.

### 5.5 Publisher / places / date / edition

Mined from the imprint block, typically pages 2..`pages`. Heuristics:

- **Publisher** — line containing imprint keywords (`Press`, `Books`, `Publishing`, named imprints like `Verso`, `Penguin`, `Routledge`); or text immediately after `Published by`.
- **Places** — recognised city names, often paired with country codes or addresses (`London`, `London, UK`, `New York, NY`). Collected as `list[str]` ordered as printed. Flag `MULTIPLE_PLACES_DETECTED` when two or more found.
- **Date** — most-recent copyright year (`© 2003`, `Copyright © 2003`) → `date`. Oldest distinct copyright year → `first_published`. If only one year present, `first_published` stays `None`.
- **Edition** — string after `Edition` keyword or in a recognised edition phrase (`Second Paperback Edition`, `Revised Edition`).

If the imprint block isn't found within pages 1..`pages`, return partial `BookMetadata` with `warnings=[INCOMPLETE_EXTRACTION (detail="imprint not found in first N pages")]`.

### 5.6 Language

Default `"en"` in M2.0. No automatic detection — would need a fragile heuristic or a dependency. Document the limitation; the EPUB path is the one with a real `dc:language` signal.

## 6. EPUB extractor (`EpubMetadataExtractor`)

### 6.1 Pipeline

```
EPUB path
  ├─► zipfile.ZipFile.is_zipfile? false → BookMetadata(error=MALFORMED_EPUB)
  ├─► META-INF/encryption.xml present + Adobe/Apple DRM ns? → BookMetadata(error=DRM_PROTECTED)
  ├─► META-INF/container.xml → OPF path; missing → BookMetadata(error=MALFORMED_EPUB)
  ├─► xml.etree.ElementTree.parse(opf) — <metadata>:
  │       ├─► dc:title → title (raw, whitespace-normalised)
  │       ├─► dc:creator + opf:role / EPUB3 refines → list[Creator]
  │       ├─► dc:publisher → publisher
  │       ├─► dc:date by opf:event / dc:rights © year → date, first_published
  │       ├─► dc:language → language (normalise BCP-47 to primary subtag)
  │       ├─► dc:identifier urn:isbn + <meta name="isbn"> → identifier (print)
  │       └─► <meta name="eisbn"> → candidates (EditionHint.EBOOK)
  ├─► TITLE-PAGE FALLBACK if dc:title is bare → split subtitle from title-page xhtml
  └─► WARNINGS aggregated → BookMetadata
```

Exceptions raised inside `ElementTree` or `zipfile` are caught at the extractor boundary and translated to `BookMetadata(error=MALFORMED_EPUB, warnings=[INCOMPLETE_EXTRACTION (detail=str(e))])`.

### 6.2 Identifier extraction

- `<meta name="isbn">` → `identifier.value` (print ISBN, the lookup-relevant one).
- `<meta name="eisbn">` → entry in `candidates` with `EditionHint.EBOOK`.
- `dc:identifier` with `opf:scheme="ISBN"` or `urn:isbn:` prefix → collected; deduplicated against the above by canonical (digits-only) form.
- Other `dc:identifier` schemes (UUID, custom publisher IDs) — silently ignored. Not flagged.
- If only an eISBN is present, it becomes `identifier.value` by default (no alternative).

### 6.3 Creators

- EPUB2: `<dc:creator opf:role="aut">Text</dc:creator>`.
- EPUB3: `<dc:creator id="creator-1">Text</dc:creator>` + `<meta refines="#creator-1" property="role">aut</meta>`.

Role mapping: `aut` → `AUTHOR`; `edt` → `EDITOR`; `trl` → `TRANSLATOR`; `ill` → `ILLUSTRATOR`. Missing role attribute → `AUTHOR`.

Name parsing:

- Prefer `opf:file-as` attribute (sort-form, `"Finkelstein, Norman"`). Split on first `, ` → `(last, first)`.
- Else parse element text the same way.
- Strip trailing whitespace and punctuation: `;`, `,`, `.` (plus trailing spaces). Trailing periods are routine on initials and abbreviations (`"Smith, J."`, `"Jones, M.A."`) — strip silently. Flag `DC_CREATOR_TRAILING_PUNCTUATION` **only** when a `;` or `,` was stripped (the Gaza case: `"Finkelstein, Norman; "`).
- `raw` always populated with the original element text (pre-strip).
- Multi-creator strings (`"Smith, J. and Jones, K."` in one `dc:creator`) — split on ` and ` then parse each as a Creator.
- **Source order preserved.** Multiple creators are returned in OPF element order (and within a multi-creator string, in the order they appeared in the string). No alphabetical or otherwise re-ordering — citation order is meaningful.

### 6.4 Date

- `dc:date` with `opf:event="publication"` → `date`. (EPUB3 uses `<meta property="dcterms:issued">` instead — handle both.)
- `dc:date` with `opf:event="original-publication"` → `first_published`. (EPUB3: `<meta property="dcterms:created">`.)
- Else first `dc:date` → `date`.
- Else extract 4-digit year from `dc:rights` (e.g., `"Copyright © 2018 by..."`) → `date`.

### 6.5 Language

`dc:language` → primary subtag of the BCP-47 tag. `"en-US"` → `"en"`; `"fr-CA"` → `"fr"`. Flag `LANGUAGE_NORMALISED` whenever the input differed from the output.

### 6.6 Title-page fallback (subtitle hunt)

When `dc:title` is short and unlikely to include a subtitle (Gaza case: `<dc:title>Gaza</dc:title>` while the title page reads `"Gaza: An Inquest Into Its Martyrdom"`):

1. Find the title-page xhtml:
   - First: OPF `<guide type="title-page">` `href`.
   - Else: OPF `<guide type="cover">` `href`.
   - Else: scan ZIP entries for `*itle*.xhtml` or `titlepage.xhtml` at OEBPS root.
2. Parse with `xml.etree.ElementTree`; collect `h1`, `h2`, `title` element text.
3. Longest non-empty string is the candidate full-title.
4. If candidate contains `dc:title` as a prefix followed by `:`, `—`, or newline → split: prefix → `title`, remainder → `subtitle`. Flag `SUBTITLE_NOT_IN_OPF`.
5. If no fallback succeeds, leave `subtitle = None`.

Compose `full_title` after the fallback (whether or not the fallback found a subtitle).

## 7. Error and warning handling

### 7.1 Always-return contract

Both extractors implement `MetadataExtractor.extract_metadata` such that **it never raises on file-shape failures**. Library exceptions (`pypdf.errors.PdfReadError`, `xml.etree.ElementTree.ParseError`, `zipfile.BadZipFile`) and domain conditions (encryption flag, missing OPF, DRM namespace) are caught and translated to `BookMetadata(error=…, warnings=…)`.

Programmer errors raise at `detect_format` (file not found, unsupported extension, magic-bytes mismatch) — before any extractor is reached.

Truly unexpected exceptions propagate to the caller. Those are bugs in the tool.

### 7.2 `error` and `warnings` interplay

| Outcome | `error` | `warnings` | Other fields |
|---|---|---|---|
| Clean extraction | `None` | `[]` | populated |
| Heuristic / partial | `None` | non-empty | populated (some may be `None`) |
| Hard failure | non-`None` | possibly non-empty (detail) | at defaults (`None` / `[]`) |

The caller checks `m.error is not None` for hard failures, then `m.warnings` for partial-extraction concerns.

### 7.3 Logging

Each extractor module uses `logger = logging.getLogger(__name__)`, matching `pdf_docling.py:33`. Internal exceptions logged at `WARNING`; progress at `INFO` (e.g., `"PDF /Info had title 'X'; falling back to text-mining"`). No `print()`. Never raise on caught conditions.

## 8. Testing strategy

Three layers, matching existing `tests/` conventions (`@pytest.mark.slow`, `@pytest.mark.real_book`).

### 8.1 Fast unit tests (no I/O)

Isolated function tests for: identifier parsers (DOI / arXiv / ISBN), ISBN canonicalization, edition-hint windowed classification, edition-priority picking, title line-joining, creator name parsing (both `"First Last"` and `"Last, First"` forms), `dc:date` event selection, language normalisation, Pydantic schema (defaults, JSON serialization, closed-vocab validation).

Budget: <100 ms per test; full fast suite under 2 s.

### 8.2 Synthetic-fixture integration tests

Build deterministic fixtures in code; no committed binaries.

```
tests/fixtures/
  pdf.py        # reportlab helpers (already in dev extras)
  epub.py       # stdlib zipfile + handwritten OPF strings
```

Helpers (illustrative):

```python
build_pdf_with_imprint(title, subtitle, isbn_paperback, isbn_hardback,
                       publisher, places, year)
build_pdf_with_all_caps_title(title_lines, subtitle)
build_encrypted_pdf(password)
build_scanned_pdf()                                  # no embedded text

build_epub(dc_title, creators, isbn, publisher, language, ...)
build_epub_with_truncated_title(dc_title, full_title_in_xhtml)
build_epub_with_drm()
build_malformed_epub()
```

Each test exercises one path end-to-end against a single synthetic fixture. Budget: <1 s per test.

### 8.3 Real-fixture acceptance (`@slow @real_book`)

Two tests, one per fixture from skill side, with values pinned from an exploratory run:

- **`test_holocaust_industry_pdf`** — asserts `identifier.value` is the paperback ISBN, `title` is the raw ALL-CAPS string, `subtitle` is the raw ALL-CAPS subtitle, `full_title` composed, `WarningCode.TITLE_ALL_CAPS_IN_SOURCE` in warnings, `publisher == "Verso"`, `places == ["London", "New York"]`, `date == "2003"`, `first_published == "2000"`.
- **`test_gaza_epub`** — asserts `identifier.value == "9780520295711"`, `candidates` contains the eISBN with `EditionHint.EBOOK`, `title == "Gaza"`, `subtitle == "An Inquest Into Its Martyrdom"`, one `Creator` with `last_name="Finkelstein"` and `raw="Finkelstein, Norman; "`, `language == "en"`, warnings include `LANGUAGE_NORMALISED`, `DC_CREATOR_TRAILING_PUNCTUATION`, `SUBTITLE_NOT_IN_OPF`.

Pinned values from a one-time exploratory run. If a change shifts them later, the test surfaces the regression; we then decide whether the change was intended.

### 8.4 Coverage targets (qualitative)

- Every `ErrorCode` member fired by at least one test.
- Every `WarningCode` member fired by at least one test.
- Public `extract_metadata` has a happy-path test for each format and at least one error-path test for each format.
- Both extractors have at least one synthetic-fixture integration test plus the real-fixture acceptance test.

### 8.5 TDD

Per `superpowers:test-driven-development`: red → green → refactor. The implementation plan (next step, `writing-plans`) will sequence test-then-code per component.

## 9. Open items for next round

These are deliberately deferred to a follow-up brainstorming pass once we have more fixtures:

- Multi-edition-ISBN PDF heuristic (paperback vs hardback vs eBook discrimination on a single PDF where multiple ISBNs are present *with different edition hints*). Holocaust Industry has multi-ISBNs but both are paperback — doesn't exercise the heuristic.
- Mixed-case PDF title fallback (§5.3 second sub-path). Heuristic and untested by a real fixture — Holocaust Industry exercises the ALL-CAPS path, not this one. Harden when a mixed-case PDF without `/Info /Title` appears in the wild.
- Adversarial EPUB shapes (unusual OPF locations, malformed OPF, deeply-nested OEBPS, multi-creator strings beyond `Smith, J. and Jones, K.`).
- Scanned-PDF route to OCR — currently returns `NO_TEXT_EXTRACTED` warning; M3 will provide an OCR fallback path.

## 10. Non-goals (restated)

- LLM calls in `extract_metadata`'s default path.
- Caching of `BookMetadata` results.
- HTTP lookup or retry logic (owned by `zotero-mcp`).
- A `BookSurvey.metadata` schema bump (deferred to M2.1).
- Auto title-casing of ALL-CAPS source strings.
- A `primary_place` field.
