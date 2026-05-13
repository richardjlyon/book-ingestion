"""Verify that importing extract_metadata does not pull in the Docling backend.

Uses a subprocess so sys.modules starts completely clean — no cross-test
contamination from other tests that may have already imported Docling.
"""
from __future__ import annotations

import subprocess
import sys


def test_extract_metadata_does_not_import_docling_backend() -> None:
    """Verify via subprocess that importing extract_metadata doesn't pull Docling backend."""
    code = (
        "import sys\n"
        "from book_ingestion import extract_metadata  # noqa: F401\n"
        "assert 'book_ingestion.backends.pdf_docling' not in sys.modules, "
        "    'PDF backend leaked into the metadata import path'\n"
        "assert 'docling' not in sys.modules, "
        "    'docling leaked into the metadata import path'\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
