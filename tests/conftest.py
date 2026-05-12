"""Shared test fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    """A clean cache directory scoped to the test."""
    d = tmp_path / "cache"
    d.mkdir()
    return d


@pytest.fixture
def synthetic_pdf(tmp_path: Path) -> Path:
    """A 1-page PDF with 3 paragraphs; deterministic content."""
    path = tmp_path / "synthetic.pdf"
    c = canvas.Canvas(str(path), pagesize=LETTER)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, 720, "Chapter 1 - The Beginning")
    c.setFont("Helvetica", 10)
    c.drawString(72, 690, "This is the first paragraph of the chapter.")
    c.drawString(72, 670, "Here is a second paragraph with more content.")
    c.drawString(72, 650, "And a third to round out the page.")
    c.showPage()
    c.save()
    return path
