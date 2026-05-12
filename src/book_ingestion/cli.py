"""Typer-based CLI: book-ingest survey | extract | cache.

JSON to stdout. Logs and errors to stderr. Exit codes:
  0 — success
  2 — extraction refused (degraded JSON still emitted)
  1 — hard error
"""
# ruff: noqa: B008 — Typer's standard pattern uses callable defaults (typer.Option / Argument).
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import typer

from book_ingestion import extract_chapter, survey
from book_ingestion.cache import Cache, default_cache_root
from book_ingestion.detect import detect_format
from book_ingestion.ir import BookSurvey, ChapterContent

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
cache_app = typer.Typer(help="Cache management")
app.add_typer(cache_app, name="cache")


def _print_json(payload: dict[str, Any]) -> None:
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
    json_schema: str | None = typer.Option(
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
        detect_format(path)  # rejects unsupported formats early with ValueError
        s = survey(path, cache_dir=cache_dir, use_cache=not no_cache, llm_assist=llm_assist)
    except typer.Exit:
        # Don't double-handle our own controlled exits (e.g. from _err paths above).
        raise
    except ValueError as e:
        _err(str(e), kind="value_error")
        raise typer.Exit(1) from e
    except Exception as e:  # boundary handler — surfaces any backend failure as exit 1
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
        detect_format(path)
        c = extract_chapter(path, chapter, cache_dir=cache_dir, use_cache=not no_cache)
    except typer.Exit:
        # Don't double-handle our own controlled exits.
        raise
    except IndexError as e:
        _err(str(e), kind="index_error")
        raise typer.Exit(1) from e
    except ValueError as e:
        _err(str(e), kind="value_error")
        raise typer.Exit(1) from e
    except Exception as e:  # boundary handler — surfaces any backend failure as exit 1
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
    path: Path | None = typer.Argument(None),
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
