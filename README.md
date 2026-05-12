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
