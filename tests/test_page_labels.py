"""Tests for page-label extraction."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

from book_ingestion.page_labels import infer_page_labels_from_blocks, read_pdf_page_labels


def _make_pdf_without_labels(path: Path) -> None:
    """Create a minimal 3-page PDF with no /PageLabels via ReportLab."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=LETTER)
    for n in range(3):
        c.drawString(72, 720, f"Page {n+1}")
        c.showPage()
    c.save()


def _make_pdf_with_labels(path: Path) -> None:
    """Build a 4-page PDF whose /PageLabels says: i, ii, 1, 2."""
    _make_pdf_without_labels(path)  # base 3-page; we'll pad to 4 below

    reader = PdfReader(str(path))
    writer = PdfWriter()
    for p in reader.pages:
        writer.add_page(p)
    writer.add_blank_page(width=612, height=792)

    # /PageLabels: { /Nums [ 0 << /S /r >> 2 << /S /D >> ] }
    nums = ArrayObject([
        NumberObject(0),
        DictionaryObject({NameObject("/S"): NameObject("/r")}),  # roman lower
        NumberObject(2),
        DictionaryObject({NameObject("/S"): NameObject("/D")}),  # decimal
    ])
    page_labels = DictionaryObject({NameObject("/Nums"): nums})
    # Reach into the writer's catalog to attach /PageLabels — test-only wiring.
    writer._root_object[NameObject("/PageLabels")] = page_labels

    with path.open("wb") as f:
        writer.write(f)


def test_returns_none_when_pdf_has_no_page_labels(tmp_path: Path) -> None:
    p = tmp_path / "no_labels.pdf"
    _make_pdf_without_labels(p)
    assert read_pdf_page_labels(p) is None


def test_returns_mapping_when_pdf_has_page_labels(tmp_path: Path) -> None:
    p = tmp_path / "with_labels.pdf"
    _make_pdf_with_labels(p)
    labels = read_pdf_page_labels(p)
    assert labels is not None
    assert labels[1] in {"i", "I"}
    assert labels[2] in {"ii", "II"}
    assert labels[3] == "1"
    assert labels[4] == "2"


def test_returns_none_on_malformed_pdf(tmp_path: Path) -> None:
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"not a pdf at all")
    assert read_pdf_page_labels(p) is None


def test_infer_arabic_progression() -> None:
    page_texts = {
        1: ["1", "Introduction"],
        2: ["chapter title", "2"],
        3: ["3", "more content"],
        4: ["4", "still more"],
        5: ["5", "etc"],
    }
    labels = infer_page_labels_from_blocks(page_texts)
    assert labels is not None
    assert labels[1] == "1"
    assert labels[5] == "5"


def test_infer_returns_none_when_no_signal() -> None:
    page_texts = {
        1: ["The quick brown fox", "jumps over"],
        2: ["the lazy dog", "and runs"],
        3: ["into the night", "alone"],
        4: ["forever", "and ever"],
    }
    assert infer_page_labels_from_blocks(page_texts) is None


def test_infer_requires_min_run_length() -> None:
    page_texts = {
        1: ["1"],
        2: ["2"],
        3: ["3"],
    }
    assert infer_page_labels_from_blocks(page_texts) is None


def test_infer_rejects_non_monotone() -> None:
    page_texts = {
        1: ["10"],
        2: ["5"],
        3: ["7"],
        4: ["12"],
    }
    assert infer_page_labels_from_blocks(page_texts) is None


def test_infer_finds_progression_inside_noisy_input() -> None:
    page_texts = {
        1: ["Front matter title"],
        2: ["acknowledgments"],
        3: ["preface"],
        4: ["1", "running header text"],
        5: ["2", "more"],
        6: ["3", "stuff"],
        7: ["4", "more stuff"],
        8: ["5", "etc"],
    }
    labels = infer_page_labels_from_blocks(page_texts)
    assert labels is not None
    assert labels[4] == "1"
    assert labels[8] == "5"
    assert 1 not in labels


def test_infer_fills_gaps_with_dominant_offset() -> None:
    """Gaps in the candidate stream (e.g., chapter-cover pages with no page
    number) are filled in by extrapolating the dominant offset."""
    page_texts = {
        15: ["11", "running header"],
        16: ["12"],
        17: ["13"],
        18: ["14"],
        19: ["chapter cover, no number"],   # gap
        20: ["16"],
        21: ["17"],
        22: ["18"],
    }
    labels = infer_page_labels_from_blocks(page_texts)
    assert labels is not None
    assert labels[15] == "11"
    assert labels[19] == "15"   # filled in via offset -4
    assert labels[22] == "18"
    # All 8 pages get labels
    assert len(labels) == 8
