"""PDF metadata extractor — pypdf-based.

Implements `MetadataExtractor` for PDFs. Reads `/Info` and the first N
pages of text. No Docling on this path.

See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §5.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

from book_ingestion.metadata import (
    BookMetadata,
    Creator,
    CreatorRole,
    EditionHint,
    ErrorCode,
    Identifier,
    IdentifierCandidate,
    IdentifierKind,
    MetadataWarning,
    WarningCode,
    canonicalize_isbn,
    classify_edition_hint,
    dedupe_isbn_candidates,
    pick_identifier_value,
)

if TYPE_CHECKING:
    from pypdf import PdfReader

logger = logging.getLogger(__name__)

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_ARXIV_RE = re.compile(r"(?:arXiv:\s*|arxiv\.org/abs/)(\d{4}\.\d{4,5})", re.IGNORECASE)
_ISBN13_RE = re.compile(r"(?:ISBN[ -]*)?(97[89][- 0-9]{10,})", re.IGNORECASE)
_ISBN10_RE = re.compile(r"(?:ISBN[ -]*)?([0-9][- 0-9]{8,10}[0-9X])", re.IGNORECASE)

_ROLE_PREFIXES: dict[str, CreatorRole] = {
    "translated by ": CreatorRole.TRANSLATOR,
    "edited by ": CreatorRole.EDITOR,
    "with foreword by ": CreatorRole.FOREWORD,
    "with a foreword by ": CreatorRole.FOREWORD,
    "illustrated by ": CreatorRole.ILLUSTRATOR,
}

_PUBLISHER_KEYWORDS = ("Press", "Books", "Publishing", "Verso", "Penguin", "Routledge")
_KNOWN_PLACES = (
    "London", "New York", "Cambridge", "Oxford", "Boston", "Chicago",
    "Edinburgh", "Glasgow", "Manchester", "Paris", "Berlin", "Rome",
    "Washington", "Toronto", "Sydney", "Melbourne", "Dublin", "Tokyo",
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_EDITION_RE = re.compile(
    r"((?:First|Second|Third|Fourth|Fifth|Revised|Updated|Paperback|Hardback)"
    r"(?:[^\S\n]+\w+)*?[^\S\n]+Edition)",
    re.IGNORECASE,
)


def _extract_identifier(text: str, warnings: list[MetadataWarning]) -> Identifier:
    """Extract identifier from text: DOI, arXiv, or ISBN."""
    # DOI — first match
    doi_m = _DOI_RE.search(text)
    if doi_m:
        value = doi_m.group(0)
        return Identifier(
            kind=IdentifierKind.DOI,
            value=value,
            candidates=[IdentifierCandidate(kind=IdentifierKind.DOI, value=value)],
        )

    # arXiv — first match
    arxiv_m = _ARXIV_RE.search(text)
    if arxiv_m:
        value = arxiv_m.group(1)
        return Identifier(
            kind=IdentifierKind.ARXIV,
            value=value,
            candidates=[IdentifierCandidate(kind=IdentifierKind.ARXIV, value=value)],
        )

    # ISBNs — gather all matches, classify by window, then dedupe.
    raw_candidates: list[IdentifierCandidate] = []
    for m in _ISBN13_RE.finditer(text):
        raw = m.group(1)
        canon = canonicalize_isbn(raw)
        if len(canon) != 13 or not canon.startswith(("978", "979")):
            continue
        window = text[max(0, m.start() - 20) : m.end() + 20]
        raw_candidates.append(IdentifierCandidate(
            kind=IdentifierKind.ISBN, value=canon,
            edition_hint=classify_edition_hint(window),
        ))
    for m in _ISBN10_RE.finditer(text):
        raw = m.group(1)
        canon = canonicalize_isbn(raw)
        if len(canon) != 10:
            continue
        # Note: no need to filter ISBN-10s that look like a substring of an
        # earlier ISBN-13 match. The length-10 filter above plus
        # `dedupe_isbn_candidates` already handle the collision case correctly:
        # for a same-book pair, the ISBN-13's last 10 digits ≠ the ISBN-10
        # (different check digit), and dedupe collapses by ISBN-13 form.
        window = text[max(0, m.start() - 20) : m.end() + 20]
        raw_candidates.append(IdentifierCandidate(
            kind=IdentifierKind.ISBN, value=canon,
            edition_hint=classify_edition_hint(window),
        ))

    if not raw_candidates:
        return Identifier()

    deduped = dedupe_isbn_candidates(raw_candidates)
    if len(deduped) > 1:
        warnings.append(MetadataWarning(
            code=WarningCode.MULTIPLE_ISBNS_DETECTED,
            detail=f"{len(deduped)} distinct ISBN editions detected",
        ))

    isbn_value = pick_identifier_value(deduped)
    return Identifier(
        kind=IdentifierKind.ISBN if isbn_value else None,
        value=isbn_value,
        candidates=deduped,
    )


def _info_title(reader: PdfReader, path: Path) -> str | None:
    """Return /Info /Title if present, non-empty, and not equal to path.stem."""
    info = reader.metadata
    if info is None:
        return None
    raw = info.get("/Title")
    if not raw:
        return None
    text = str(raw).strip()
    if not text or text == path.stem or text.lower() == "untitled":
        return None
    return text


def _is_all_caps(line: str) -> bool:
    has_letter = any(c.isalpha() for c in line)
    return has_letter and line.upper() == line


def _mine_title_from_page_one(text_page_one: str) -> tuple[str | None, str | None]:
    """Return (title, subtitle) from page-1 text mining.

    Strategy (spec §5.3):
      - Find first ALL-CAPS block (consecutive ALL-CAPS lines without trailing punct).
        Join with single spaces. Subtitle = next ALL-CAPS block before author signal.
      - Else, first non-trivial line (≥5 chars, not a page number).
        Subtitle = next non-empty line if shorter than title.
    """
    lines = [line.strip() for line in text_page_one.splitlines() if line.strip()]
    if not lines:
        return None, None

    # ALL-CAPS path: collect consecutive ALL-CAPS lines without trailing punct.
    # Each run of consecutive ALL-CAPS lines forms a block; blocks are separated by
    # non-ALL-CAPS lines, author signal, or when a line looks like a standalone subtitle
    # (relatively long, all-caps line following another relatively long all-caps line).
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.lower().startswith("by "):
            break
        if _is_all_caps(line):
            # Check if this looks like a standalone subtitle:
            # if current block has >= 1 line AND both current[-1] and this line are >= 15 chars
            # and neither has trailing punct, then finalize current and start a new block.
            should_break_before = (
                current
                and len(current[0]) >= 15
                and len(line) >= 15
                and not (current[-1] and current[-1][-1] in ".,:;!?")
                and not (line and line[-1] in ".,:;!?")
            )
            if should_break_before:
                blocks.append(current)
                current = []
            current.append(line)
        else:
            if current:
                blocks.append(current)
                current = []
            # Continue scanning — later ALL-CAPS may be subtitle.
    if current:
        blocks.append(current)

    if blocks:
        title = " ".join(blocks[0])
        subtitle = " ".join(blocks[1]) if len(blocks) > 1 else None
        return title, subtitle

    # First non-trivial line fallback
    for line in lines:
        if len(line) < 5:
            continue
        if line.isdigit():
            continue
        title = line
        # Subtitle: next non-empty line shorter than title
        idx = lines.index(line)
        rest = lines[idx + 1 :]
        for r in rest:
            if r.lower().startswith("by "):
                break
            if 0 < len(r) < len(title):
                return title, r
        return title, None
    return None, None


def _compose_full_title(title: str | None, subtitle: str | None) -> str | None:
    if title is None:
        return None
    if subtitle is None:
        return title
    return f"{title}: {subtitle}"


def _parse_one_name(raw: str) -> Creator:
    """Parse a single creator name string into a Creator (role=AUTHOR; caller may override)."""
    stripped = raw.strip().rstrip(",;")
    if "," in stripped:
        # "Last, First [Middle]"
        last, _, first = stripped.partition(",")
        last_name = last.strip() or None
        first_name = first.strip() or None
    else:
        parts = stripped.rsplit(None, 1)
        if len(parts) == 2:
            first_name, last_name = parts[0].strip() or None, parts[1].strip() or None
        else:
            first_name, last_name = None, stripped or None
    return Creator(first_name=first_name, last_name=last_name, raw=raw)


def _split_creator_string(text: str) -> list[str]:
    """Split a creator string on ' and ' first, then on commas (when likely two people)."""
    # First split on ' and '
    parts = [p.strip() for p in re.split(r"\s+and\s+", text) if p.strip()]
    # If only one part remains, try comma split as a fallback for "X, Y, Z" lists.
    # (Don't split on commas if the part contains a comma-form name with no 'and' —
    # that produces a single Creator; comma-list authors typically use 'and' too.)
    return parts


def _is_likely_author_line(raw: str) -> bool:
    """Heuristic: line is a plausible standalone author name.

    Returns True for lines like:
      "Norman G. Finkelstein"
      "NORMAN G. FINKELSTEIN"
      "Jane Smith"
      "J. R. R. Tolkien"
    Returns False for lines with digits, too few/many tokens, or
    lowercase-start tokens.
    """
    if any(c.isdigit() for c in raw):
        return False
    tokens = raw.split()
    if not (2 <= len(tokens) <= 5):
        return False
    for tok in tokens:
        stripped = tok.rstrip(".")
        if not stripped:
            return False
        first = stripped[0]
        rest = stripped[1:]
        # Each token must start with a capital, and the rest must be all-caps,
        # all-lower (proper-noun case), or empty (single-letter initial).
        if not first.isupper():
            return False
        if rest and not (rest.isupper() or rest.islower()):
            return False
    return True


def _extract_creators(
    text_page_one: str,
    *,
    title: str | None = None,
    subtitle: str | None = None,
) -> list[Creator]:
    """Find a creator line on page 1 and parse it into Creator objects."""
    lines = [line.strip() for line in text_page_one.splitlines() if line.strip()]
    exclude = {title or "", subtitle or ""}

    for raw in lines:
        lowered = raw.lower()
        matched_role: CreatorRole | None = None
        remainder = raw
        for prefix, role in _ROLE_PREFIXES.items():
            if lowered.startswith(prefix):
                matched_role = role
                remainder = raw[len(prefix):]
                break
        if matched_role is None and lowered.startswith("by "):
            remainder = raw[3:]
            matched_role = CreatorRole.AUTHOR
        if matched_role is None:
            continue

        parts = _split_creator_string(remainder)
        creators: list[Creator] = []
        for part in parts:
            c = _parse_one_name(part)
            creators.append(c.model_copy(update={"role": matched_role}))
        if creators:
            return creators

    # No explicit role prefix — try comma-form "Last, First" on a standalone line.
    for raw in lines:
        if re.match(r"^[A-Z][A-Za-z\-]+,\s*[A-Z]", raw):
            return [_parse_one_name(raw)]

    # Last resort: standalone name-like line (e.g. ALL-CAPS "NORMAN G. FINKELSTEIN").
    for raw in lines:
        if raw in exclude:
            continue
        # Skip lines that look like edition phrases (e.g. "Second Paperback Edition")
        if _EDITION_RE.fullmatch(raw.strip()):
            continue
        if _is_likely_author_line(raw):
            return [_parse_one_name(raw)]

    return []


def _extract_publisher(imprint_text: str) -> str | None:
    """Extract publisher from imprint text.

    First checks for 'Published by ' prefix; else looks for any imprint keyword.
    Prefers the shortest matching line (standalone publisher name beats a long
    description like 'First published by Verso 2000').
    """
    best: str | None = None
    for line in imprint_text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        low = cleaned.lower()
        if low.startswith("published by "):
            candidate = cleaned[len("Published by "):].strip()
            if best is None:
                best = candidate
            continue
        for kw in _PUBLISHER_KEYWORDS:
            if kw not in cleaned:
                continue
            # Prefer shorter lines: a standalone "Verso" beats "First published by Verso 2000"
            if best is None or len(cleaned) < len(best):
                best = cleaned
            break
    return best


def _extract_places(imprint_text: str) -> list[str]:
    """Extract known place names from imprint text."""
    places: list[str] = []
    for line in imprint_text.splitlines():
        for known in _KNOWN_PLACES:
            if known in line and known not in places:
                places.append(known)
    return places


def _extract_dates(imprint_text: str) -> tuple[str | None, str | None]:
    """Return (date, first_published).

    Strategy: scan all 4-digit years in the imprint block; take max as `date`
    (most recent edition) and min as `first_published` when there are multiple
    distinct years; single year → `date` only.

    The imprint block is deliberately limited to the 2 pages immediately
    following the title page, so incidental years from blurb/review pages are
    excluded before this function is called.
    """
    years = sorted({m.group(0) for m in _YEAR_RE.finditer(imprint_text)})
    if not years:
        return None, None
    if len(years) == 1:
        return years[0], None
    return years[-1], years[0]  # most recent → date; earliest → first_published


def _extract_edition(imprint_text: str) -> str | None:
    """Extract edition phrase from imprint text via regex.

    When multiple edition phrases appear (e.g. "First paperback edition …
    Second paperback edition"), returns the last match — mirroring the
    latest-wins semantics of _extract_dates.
    """
    matches = _EDITION_RE.findall(imprint_text)
    return matches[-1] if matches else None


class PdfMetadataExtractor:
    """PDF metadata extractor.

    `extract_metadata` always returns a BookMetadata; it does not raise on
    file-shape failures. See spec §7.
    """

    name = "pdf_pypdf"

    def extract_metadata(self, path: Path, *, pages: int = 6) -> BookMetadata:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(str(path))
        except (PdfReadError, OSError) as exc:
            logger.warning("pypdf failed to open %s: %s", path, exc)
            return BookMetadata(
                error=ErrorCode.MALFORMED_PDF,
                warnings=[MetadataWarning(
                    code=WarningCode.INCOMPLETE_EXTRACTION, detail=str(exc),
                )],
            )

        if reader.is_encrypted:
            return BookMetadata(error=ErrorCode.ENCRYPTED)

        # Pull text from up to `pages` leading pages.
        page_texts: list[str] = []
        for i, page in enumerate(reader.pages):
            if i >= pages:
                break
            try:
                page_texts.append(page.extract_text() or "")
            except Exception as exc:  # pypdf can raise on malformed streams
                logger.warning("pypdf failed to extract page %d of %s: %s", i, path, exc)
                page_texts.append("")

        joined = "\n".join(page_texts).strip()
        if not joined:
            return BookMetadata(warnings=[
                MetadataWarning(
                    code=WarningCode.NO_TEXT_EXTRACTED,
                    detail="PDF has no embedded text (scanned or empty)",
                ),
            ])

        # Subsequent tasks populate title, creators, etc.
        warnings: list[MetadataWarning] = []

        # Find the first non-empty page for title/creator mining. Real books
        # often have a blank page 0 (verso/half-title) with the full title page
        # on page 1.
        title_page_text = ""
        title_page_idx = 0
        for idx, pt in enumerate(page_texts):
            if pt.strip():
                title_page_text = pt
                title_page_idx = idx
                break

        identifier = _extract_identifier(joined, warnings)

        # Title strategy:
        #   1. Always text-mine the title page for ALL-CAPS detection and subtitle.
        #   2. If /Info is present, compare with text-mined result:
        #      a. If they are the same title in different case (text-mined is
        #         ALL-CAPS, /Info is mixed-case) → prefer text-mined (calibre
        #         and similar converters normalise the case, losing the source
        #         formatting).
        #      b. If text-mined starts with /Info and is longer → text mining
        #         merged title+subtitle; split at /Info boundary.
        #      c. Otherwise → use /Info as title; use any text-mined subtitle.
        #   3. If no /Info: use text-mined title/subtitle.
        #   4. Fallback: None.
        mined_title, mined_subtitle = _mine_title_from_page_one(title_page_text)
        info_title = _info_title(reader, path)
        title: str | None
        subtitle: str | None
        if info_title is not None and mined_title is not None:
            mined_upper = mined_title.upper()
            info_upper = info_title.upper()
            if mined_upper == info_upper:
                # Same title, different case: prefer ALL-CAPS source form.
                title = mined_title
                subtitle = mined_subtitle
            elif mined_title.upper().startswith(info_upper) and len(mined_title) > len(info_title):
                # Text mining merged title+subtitle into one block; split it.
                title = info_title
                remainder = mined_title[len(info_title):].lstrip()
                subtitle = remainder if remainder else mined_subtitle
            else:
                title = info_title
                subtitle = mined_subtitle
        elif info_title is not None:
            title = info_title
            subtitle = None
        elif mined_title is not None:
            title = mined_title
            subtitle = mined_subtitle
        else:
            title = None
            subtitle = None

        if title is not None and _is_all_caps(title):
            warnings.append(MetadataWarning(code=WarningCode.TITLE_ALL_CAPS_IN_SOURCE))

        full_title = _compose_full_title(title, subtitle)

        creators = _extract_creators(title_page_text, title=title, subtitle=subtitle)

        # Imprint block: at most the 2 pages immediately following the title
        # page (indices title_page_idx+1 .. title_page_idx+2). Limiting to 2
        # pages avoids picking up blurb/review pages that contain city names
        # (e.g. "Chicago") or incidental years (e.g. "1998") that would corrupt
        # the places and date fields.
        imprint_pages = page_texts[title_page_idx + 1 : title_page_idx + 3]
        imprint_text = "\n".join(imprint_pages)
        publisher = _extract_publisher(imprint_text)
        places = _extract_places(imprint_text)
        if len(places) > 1:
            warnings.append(MetadataWarning(code=WarningCode.MULTIPLE_PLACES_DETECTED))
        date, first_published = _extract_dates(imprint_text)
        edition = _extract_edition(imprint_text)

        # Edition-hint fallback for ISBNs: when all candidates show UNSPECIFIED,
        # derive a hint from the edition phrase found in the imprint block.
        # Real copyright pages often name the edition ("Second Paperback Edition")
        # several lines above the ISBN lines, beyond the ±20-char window.
        if edition is not None and identifier.candidates:
            all_unspecified = all(
                c.edition_hint == EditionHint.UNSPECIFIED for c in identifier.candidates
            )
            if all_unspecified:
                fallback_hint = classify_edition_hint(edition)
                if fallback_hint != EditionHint.UNSPECIFIED:
                    new_candidates = [
                        c.model_copy(update={"edition_hint": fallback_hint})
                        for c in identifier.candidates
                    ]
                    identifier = Identifier(
                        kind=identifier.kind,
                        value=identifier.value,
                        candidates=new_candidates,
                    )

        return BookMetadata(
            identifier=identifier,
            title=title,
            subtitle=subtitle,
            full_title=full_title,
            creators=creators,
            publisher=publisher,
            places=places,
            date=date,
            first_published=first_published,
            edition=edition,
            language="en",  # PDF default per spec §5.6
            warnings=warnings,
        )
