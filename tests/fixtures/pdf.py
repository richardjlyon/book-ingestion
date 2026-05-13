"""Synthetic PDF builders for tests. reportlab is in dev extras.

These helpers produce small, deterministic PDFs that exercise specific
extraction paths (imprint mining, ALL-CAPS title, encryption, no-text).
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


def build_pdf_with_imprint(
    path: Path,
    *,
    title: str,
    subtitle: str,
    isbn_paperback: str,
    isbn_hardback: str,
    publisher: str,
    places: list[str],
    year: int,
    first_published_year: int | None = None,
) -> Path:
    """Build a 3-page PDF: page 1 = title page, page 2 = copyright page, page 3 = body."""
    c = canvas.Canvas(str(path), pagesize=LETTER)
    # /Info entries
    c.setTitle(title)

    # Page 1: title page
    c.setFont("Helvetica-Bold", 24)
    c.drawString(72, 700, title)
    c.setFont("Helvetica", 16)
    c.drawString(72, 670, subtitle)
    c.showPage()

    # Page 2: copyright / imprint page
    c.setFont("Helvetica", 10)
    y = 720
    c.drawString(72, y, f"Published by {publisher}")
    y -= 14
    for place in places:
        c.drawString(72, y, place)
        y -= 14
    if first_published_year is not None:
        c.drawString(72, y, f"First published {first_published_year}")
        y -= 14
    c.drawString(72, y, f"Copyright © {year}")
    y -= 14
    c.drawString(72, y, f"Paperback ISBN {isbn_paperback}")
    y -= 14
    c.drawString(72, y, f"Hardback ISBN {isbn_hardback}")
    c.showPage()

    # Page 3: a body paragraph
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "This is the body of the book.")
    c.save()
    return path


def build_pdf_with_all_caps_title(
    path: Path,
    *,
    title_lines: list[str],
    subtitle: str | None,
    author: str,
) -> Path:
    """Build a 1-page PDF whose page 1 has an ALL-CAPS multi-line title.

    /Info /Title is intentionally left blank to force text-mining.
    """
    c = canvas.Canvas(str(path), pagesize=LETTER)
    # No setTitle() — leaves /Info /Title at the path stem
    y = 700
    c.setFont("Helvetica-Bold", 18)
    for line in title_lines:
        c.drawString(72, y, line)
        y -= 22
    y -= 8
    if subtitle is not None:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(72, y, subtitle)
        y -= 20
    y -= 12
    c.setFont("Helvetica", 12)
    c.drawString(72, y, author)
    c.save()
    return path


def build_encrypted_pdf(path: Path, *, password: str) -> Path:
    """Build a password-protected PDF."""
    c = canvas.Canvas(str(path), pagesize=LETTER, encrypt=password)
    c.setFont("Helvetica", 10)
    c.drawString(72, 720, "Encrypted content.")
    c.save()
    return path


def build_scanned_pdf(path: Path) -> Path:
    """Build a 'scanned' PDF: page exists, but no embedded text."""
    c = canvas.Canvas(str(path), pagesize=LETTER)
    # Page with only a thin line — no text.
    c.line(72, 720, 540, 720)
    c.showPage()
    c.save()
    return path
