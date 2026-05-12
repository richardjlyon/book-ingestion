# book-ingestion — what we're trying to achieve

> A statement of intent for an implementer who knows nothing about the wider system. Describes the end product, what we need to produce, and what this tool has to output to make that possible. Leaves *how* to the brainstorm.

---

## 1. The bigger picture

The user runs a personal knowledge system: domain-organised Obsidian vaults that hold structured, cross-linked content used to reason about contested topics. New material — papers, articles, datasets — gets ingested into a vault as a small set of typed files (a source record, atomic notes, concept definitions, people, journals, institutions, synthesised threads). Each file has prescribed frontmatter and a prescribed body shape. The discipline of "every fact lives in exactly one place; sources hold verbatim extracts; notes hold one claim each; threads synthesise" is enforced by an existing ingestion skill.

That skill works on **papers**: ~20–50 pages, single-pass reading, ~5–15 atomic notes per source. It does not work on **books**: 200–800 pages, ~50–200 atomic notes, chapter-level provenance, costs and context sizes that defeat single-pass reading.

The goal of this repository is to bridge that gap, so that a book can be ingested into the vault to the same standard a paper is ingested today — chapter and page resolution preserved, conciseness discipline intact, cost manageable.

---

## 2. What gets produced when a book is ingested

For each ingested book, the vault gains the following content. The shapes below are what we are trying to produce; the tool's job is to make producing them feasible.

### 2.1 A source record

One file representing the whole book. Carries book-level metadata (title, author, year, publisher, ISBN where applicable). Body holds a short factual summary of the book, the book's table of contents, and a growing collection of verbatim extracts organised by chapter. Extracts accumulate across multiple ingest sessions — the source file is appended to as chapters are processed, not written in one go.

### 2.2 Atomic notes

Many small files, one claim each. Each note states one factual or argumentative claim drawn from the book, lists counter-arguments (from the book itself or from other vault material), and cites the source. Crucially, **each note also pins the claim to a specific location in the book** — chapter, and where possible page. This is the provenance granularity papers don't need but books do: a 500-page book holds dozens of distinct claims, and a reader of the note must be able to find the supporting passage without re-reading the book.

### 2.3 Concept stubs

Short definitional files for any domain term the notes wikilink that does not already have a concept file. Definition only.

### 2.4 People, institutions, journal files

Short orientation files for any named individual, organisation, or publication venue the source introduces (including those introduced via counter-argument).

### 2.5 Thread updates

Existing threads get amended where the book's claims strengthen, qualify, or contradict them. New threads get created where the book opens a position not already captured.

### 2.6 Out-of-band artefacts

A log entry. A tag-vocabulary update if the book introduces a tag not yet in use. None of these are this tool's concern.

---

## 3. What this tool has to output to make all that possible

The downstream workflow — an LLM driven by a skill — does the actual authoring of vault content. For it to do that well on book-length sources, it needs the tool to hand it a representation of the book that has three properties.

### 3.1 A reliable structural map of the book

The workflow needs to know how the book is partitioned: what the chapters are, where each one starts and ends, and how confident we are in that partition. This is what allows the workflow to ingest one chapter at a time (the cost-control mechanism), to populate the source file's table of contents accurately, and to attach a `cite_locator` like "ch3, pp 142–145" to each note it produces.

The map should be unambiguous about its provenance: was the chapter list lifted from an embedded outline (reliable), inferred from typographic signals (less reliable), or could the tool not work it out at all (the workflow must fall back to asking the user). A wrong chapter map produces wrong locators on every note derived from the book; the workflow needs to know how much to trust what it's been given.

Book-level metadata that lets the source file's frontmatter be authored without manual reconciliation also belongs here.

### 3.2 Clean, page-aware text per chapter

For each chapter the workflow chooses to process, it needs the chapter's prose in a form the LLM can read without wading through layout debris: running headers, running footers, page numbers, mid-paragraph footnote markers, two-column reflow artefacts, soft hyphens. The text should also be page-anchored: the workflow must be able to determine which page any given sentence came from, so notes derived from that sentence carry the right page in their locator.

Beyond plain prose, structural elements that survive cleaning matter: section headings within a chapter (so longer chapters can be sub-segmented), tables (preserved in some queryable form rather than mangled into pseudo-paragraphs), figure captions (text-only; the figure itself is not vault content). Footnotes and endnotes can be either inlined or held aside, as long as the workflow can recover them when a note relies on them.

### 3.3 Honesty about extraction quality

Books vary wildly — modern academic publishing, scanned older editions, OCR'd documents of varying quality, EPUBs with semantic markup, EPUBs that are basically reflowed HTML, dual-column policy reports, books with parts containing chapters containing sections. The tool should be candid about where its extraction is reliable and where it isn't, so the workflow can decide whether to proceed, ask the user, or skip a section. Silent corruption is the worst failure mode: a note that quotes "garbled OCR text presented as if accurate" is harder to detect at audit time than a tool that refuses to extract a section it can't read cleanly.

---

## 4. What this tool explicitly is not responsible for

These belong to other parts of the system. The brainstorm should not extend the tool's scope to cover them; they're listed here so they aren't designed away.

- It does not author any vault content. It produces an intermediate representation; another agent reads that representation and writes vault files.
- It does not know what an Obsidian vault is, what a "note" or a "thread" is, or what the user's tag vocabulary is.
- It does not call an LLM in its core operation. (One narrow exception is worth considering: if a book's structure is impossible to extract cleanly without semantic help, the tool may want to invoke a model to interpret typographic signals. The brainstorm can decide whether this belongs inside this tool or above it.)
- It does not fetch books from anywhere. The user supplies a local file path.
- It does not handle physical (paper-only) books.
- It does not maintain state between invocations. The orchestration layer that decides "ingest chapter 5 today, chapter 6 tomorrow" lives above this tool.
- It does not handle the Zotero ↔ vault metadata reconciliation. That's the workflow's job, using whatever metadata this tool surfaces from the file itself.

---

## 5. Acceptance — what good looks like

This tool has done its job when an LLM-driven workflow can, given a book file path:

1. Discover the book's chapter structure with enough confidence to drive a chapter-by-chapter ingest loop.
2. Process any individual chapter into vault content (notes, extracts, concepts, etc.) without the LLM needing to compensate for layout noise, page-number debris, or ambiguous provenance.
3. Attach correct chapter and page locators to every note it creates.
4. Trust the tool to flag the cases where extraction quality is poor enough that ingestion should pause.

The same tool should serve every book shape we plausibly encounter — modern academic PDFs, older scanned-and-OCR'd PDFs, EPUBs of varying construction, policy reports with complex layouts — without each shape becoming a separate code path the user has to choose between.

How that's built, what libraries are used, what the interface looks like, what the output format is, how the project is structured, how tests are organised — all open. The brainstorm's job.

---

## 6. Context the brainstorm may find useful

- The downstream workflow that consumes this tool's output is a forthcoming Obsidian skill called `ingesting-books`. It does not exist yet. The existing paper-shaped skill it parallels lives at `/Users/rjl/Resilio/Obsidian/skills/ingesting-references/SKILL.md` and is the closest reference for the kind of vault content being produced.
- The vault's content contract (frontmatter shapes, body conventions, conciseness budgets) lives at `/Users/rjl/Resilio/Obsidian/README.md`.
- The upstream design conversation is captured at `/Users/rjl/Resilio/claude-cowork/project/book-ingestion/plan.md`. It includes options-considered for the schema and workflow that this document deliberately omits.

The brainstorm is free to ignore those references if working from this document alone is sufficient. They're provided as a safety net, not a reading list.
