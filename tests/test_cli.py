"""Tests for the CLI."""
from __future__ import annotations

import json
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
    assert "unsupported format" in (result.stderr or result.output)


@pytest.mark.slow
def test_cli_survey_emits_valid_json(synthetic_pdf: Path, tmp_cache_dir: Path) -> None:
    result = runner.invoke(
        app, ["survey", str(synthetic_pdf), "--cache-dir", str(tmp_cache_dir)]
    )
    assert result.exit_code in (0, 2), result.output
    # Click 8.2+ separates stdout/stderr; RapidOCR (used by Docling) emits INFO
    # logs to stderr which would otherwise pollute result.output. Parse stdout.
    payload = json.loads(result.stdout)
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
