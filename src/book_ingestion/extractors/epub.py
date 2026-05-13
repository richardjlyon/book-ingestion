"""EPUB metadata extractor — stdlib zipfile + xml.etree.

Implements `MetadataExtractor` for EPUBs. Reads `META-INF/container.xml`
to locate the OPF, then parses Dublin Core metadata. No external XML
library (no lxml).

See `docs/superpowers/specs/2026-05-13-extract-metadata-design.md` §6.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

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
    dedupe_isbn_candidates,
    pick_identifier_value,
)

logger = logging.getLogger(__name__)

_ADOBE_DRM_NS = "http://ns.adobe.com/adept"
_APPLE_DRM_NS = "com.apple.iBooks"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_OPF_NS = "http://www.idpf.org/2007/opf"
_CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"

_OPF_ROLE_MAP: dict[str, CreatorRole] = {
    "aut": CreatorRole.AUTHOR,
    "edt": CreatorRole.EDITOR,
    "trl": CreatorRole.TRANSLATOR,
    "ill": CreatorRole.ILLUSTRATOR,
}


def _strip_creator_punct(raw: str) -> tuple[str, bool]:
    """Strip trailing whitespace + ; , and . from a creator string.

    Returns (stripped, flag_warning) — flag is True only when `;` or `,` was stripped.
    """
    s = raw
    flag = False
    # First trim trailing whitespace and periods silently
    while s and s[-1] in (" ", "\t", "."):
        s = s[:-1]
    # Then strip ; and , and flag
    while s and s[-1] in (";", ","):
        flag = True
        s = s[:-1]
    # Strip remaining trailing whitespace again
    s = s.rstrip()
    return s, flag


def _parse_one_creator_string(raw: str, role: CreatorRole) -> Creator:
    """Parse 'Last, First' or 'First Last' into a Creator. raw is preserved."""
    stripped, _ = _strip_creator_punct(raw)
    if "," in stripped:
        last, _, first = stripped.partition(",")
        last_name = last.strip() or None
        first_name = first.strip().rstrip(".") or None
    else:
        parts = stripped.rsplit(None, 1)
        if len(parts) == 2:
            first_name = parts[0].strip() or None
            last_name = parts[1].strip() or None
        else:
            first_name, last_name = None, stripped or None
    return Creator(role=role, first_name=first_name, last_name=last_name, raw=raw)


def _split_multi_creator(s: str) -> list[str]:
    """Split 'Smith, J. and Jones, K.' into ['Smith, J.', 'Jones, K.']."""
    return [p.strip() for p in re.split(r"\s+and\s+", s) if p.strip()]


def _extract_identifier_from_opf(meta_elem: ET.Element) -> Identifier:
    """Extract ISBN identifier from dc:identifier and <meta name="isbn"|"eisbn">.

    Handles:
    - <dc:identifier opf:scheme="ISBN">...</dc:identifier>
    - <dc:identifier>urn:isbn:...</dc:identifier>
    - <meta name="isbn" content="..."/> (print ISBN, UNSPECIFIED hint)
    - <meta name="eisbn" content="..."/> (electronic ISBN, EBOOK hint)

    Returns Identifier with deduplicated candidates and selected value via pick_identifier_value.
    """
    raw_candidates: list[IdentifierCandidate] = []

    # dc:identifier with opf:scheme="ISBN" or urn:isbn: prefix
    for ident in meta_elem.findall(f"{{{_DC_NS}}}identifier"):
        text = (ident.text or "").strip()
        scheme = (ident.get(f"{{{_OPF_NS}}}scheme") or "").lower()
        is_isbn = False
        value = text
        if scheme == "isbn":
            is_isbn = True
        elif text.lower().startswith("urn:isbn:"):
            is_isbn = True
            value = text[len("urn:isbn:"):]
        if is_isbn:
            canon = canonicalize_isbn(value)
            raw_candidates.append(IdentifierCandidate(
                kind=IdentifierKind.ISBN, value=canon,
                edition_hint=EditionHint.UNSPECIFIED,
            ))

    # <meta name="isbn"> and <meta name="eisbn">
    for meta in meta_elem.findall(f"{{{_OPF_NS}}}meta"):
        name = (meta.get("name") or "").lower()
        content = meta.get("content") or ""
        if not content:
            continue
        if name == "isbn":
            raw_candidates.append(IdentifierCandidate(
                kind=IdentifierKind.ISBN, value=canonicalize_isbn(content),
                edition_hint=EditionHint.UNSPECIFIED,
            ))
        elif name == "eisbn":
            raw_candidates.append(IdentifierCandidate(
                kind=IdentifierKind.ISBN, value=canonicalize_isbn(content),
                edition_hint=EditionHint.EBOOK,
            ))

    if not raw_candidates:
        return Identifier()

    deduped = dedupe_isbn_candidates(raw_candidates)
    selected_value: str | None = pick_identifier_value(deduped)
    return Identifier(
        kind=IdentifierKind.ISBN if selected_value else None,
        value=selected_value,
        candidates=deduped,
    )


def _extract_creators_from_opf(
    meta_elem: ET.Element,
    warnings: list[MetadataWarning],
) -> list[Creator]:
    """Walk dc:creator elements in document order; resolve role; split multi-creator strings."""
    creators: list[Creator] = []
    # Build EPUB3 refines map: id -> role (for <meta refines="#id" property="role">aut</meta>)
    refines_role: dict[str, str] = {}
    for meta in meta_elem.findall(f"{{{_OPF_NS}}}meta"):
        refines = meta.get("refines", "")
        if meta.get("property") == "role" and refines.startswith("#"):
            text = (meta.text or "").strip()
            if text:
                refines_role[refines[1:]] = text

    for elem in meta_elem.findall(f"{{{_DC_NS}}}creator"):
        text = elem.text or ""
        if not text.strip():
            continue
        # Resolve role
        role_str = elem.get(f"{{{_OPF_NS}}}role") or refines_role.get(elem.get("id", ""), "aut")
        role = _OPF_ROLE_MAP.get(role_str, CreatorRole.AUTHOR)

        # Prefer opf:file-as if present
        file_as = elem.get(f"{{{_OPF_NS}}}file-as")
        base_text = file_as if file_as else text

        # Punctuation flag
        _stripped, flag = _strip_creator_punct(base_text)
        if flag and not any(w.code == WarningCode.DC_CREATOR_TRAILING_PUNCTUATION for w in warnings):
            warnings.append(MetadataWarning(
                code=WarningCode.DC_CREATOR_TRAILING_PUNCTUATION,
                detail=f"creator '{text.strip()}' had trailing ; or ,",
            ))

        # Split multi-creator strings. For name *parsing* we prefer the
        # sort-form in opf:file-as when present (it's easier to split into
        # last/first). For the `raw` field per spec §6.3, we always preserve
        # the original element text (single-creator case) or the original
        # split part (multi-creator case) — never the file-as derivation.
        parsing_source = base_text
        raw_source_full = text  # always the element text — never file_as
        parts_for_parsing = _split_multi_creator(parsing_source)
        parts_for_raw = _split_multi_creator(raw_source_full) if len(parts_for_parsing) > 1 else [raw_source_full]
        for i, parse_part in enumerate(parts_for_parsing):
            raw_part = parts_for_raw[i] if i < len(parts_for_raw) else parse_part
            # _parse_one_creator_string parses names from `raw_part`; we then
            # set `raw` explicitly so it preserves the element-text form.
            c = _parse_one_creator_string(parse_part, role)
            creators.append(c.model_copy(update={"raw": raw_part}))

    return creators


def _find_opf_path(container_xml: bytes) -> str | None:
    """Parse container.xml to find the OPF path from rootfile/@full-path."""
    try:
        root = ET.fromstring(container_xml)
    except ET.ParseError:
        return None
    rootfile = root.find(f".//{{{_CONTAINER_NS}}}rootfile")
    if rootfile is None:
        return None
    return rootfile.get("full-path")


def _normalise_language(raw: str) -> tuple[str, bool]:
    """Normalise a BCP-47 tag to its primary subtag. Returns (out, changed)."""
    primary = raw.split("-", 1)[0].lower()
    return primary, primary != raw


_YEAR_RE_EPUB = re.compile(r"\b(19|20)\d{2}\b")


def _extract_dates_from_opf(meta_elem: ET.Element) -> tuple[str | None, str | None]:
    """Return (date, first_published)."""
    publication: str | None = None
    original: str | None = None
    fallback: str | None = None

    for dc_date in meta_elem.findall(f"{{{_DC_NS}}}date"):
        event = (dc_date.get(f"{{{_OPF_NS}}}event") or "").lower()
        text = (dc_date.text or "").strip()
        if not text:
            continue
        if event == "publication":
            publication = text
        elif event == "original-publication":
            original = text
        elif fallback is None:
            fallback = text

    # EPUB3 meta refines/properties for dates
    for meta in meta_elem.findall(f"{{{_OPF_NS}}}meta"):
        prop = (meta.get("property") or "").lower()
        text = (meta.text or "").strip()
        if not text:
            continue
        if prop == "dcterms:issued" and publication is None:
            publication = text
        elif prop == "dcterms:created" and original is None:
            original = text

    if publication is not None or fallback is not None:
        date = publication or fallback
        return date, original

    # Fallback: extract a year from dc:rights
    dc_rights = meta_elem.findtext(f"{{{_DC_NS}}}rights")
    if dc_rights:
        m = _YEAR_RE_EPUB.search(dc_rights)
        if m:
            return m.group(0), None
    return None, original


def _find_title_page_href(opf_root: ET.Element, names: set[str]) -> str | None:
    """Return the EPUB-internal href of the title-page xhtml, or None.

    Checks the OPF <guide> for type='title-page' first, then falls back
    to scanning the zip's member names for any xhtml file with 'title'
    or 'titlepage' in its basename. The cover-page guide entry is skipped
    because cover pages often lack the subtitle.

    The returned value may be:
    - a relative href from the guide (e.g. 'title.xhtml')
    - a full zip-member path from the name scan (e.g. 'OEBPS/Title.xhtml')

    Callers should resolve against opf_dir, handling both forms.
    """
    # <guide type="title-page" href="..."/>
    for ref in opf_root.iter(f"{{{_OPF_NS}}}reference"):
        if (ref.get("type") or "").lower() == "title-page":
            return ref.get("href")
    # Fallback: scan zip names for *itle*.xhtml or titlepage.xhtml.
    # (Cover-page guide entries are intentionally skipped — they resolve to
    # cover images, not the title/subtitle page.)
    # Rank: exact 'title.xhtml' or 'titlepage.xhtml' basenames first, then
    # any xhtml whose basename contains 'title'.  Sorting by rank then by
    # name gives deterministic results across Python set-iteration orders.
    _RANK_EXACT = 0
    _RANK_CONTAINS = 1
    ranked: list[tuple[int, str]] = []
    for name in names:
        lowered = name.lower()
        basename = lowered.rsplit("/", 1)[-1]
        if not basename.endswith(".xhtml"):
            continue
        stem = basename[: -len(".xhtml")]
        if stem in ("title", "titlepage"):
            ranked.append((_RANK_EXACT, name))
        elif "titlepage" in basename or "title" in basename:
            ranked.append((_RANK_CONTAINS, name))
    if ranked:
        ranked.sort()
        return ranked[0][1]
    return None


def _normalize_all_caps(text: str) -> str:
    """Title-case a string that is entirely upper-case; leave mixed-case unchanged."""
    return text.title() if text.isupper() else text


def _parse_title_page_text(xhtml_bytes: bytes, dc_title: str | None = None) -> str | None:
    """Return a subtitle-splittable string from a title-page xhtml.

    Strategy:
    1. If h1 matches *dc_title* (case-insensitive) and h2 is also present,
       synthesize ``"<h1>: <h2>"`` (normalising ALL-CAPS h2 to title case).
       This handles EPUBs that place title in <h1> and subtitle in <h2>.
    2. Otherwise return the longest non-empty text found in h1 / h2 / <title>.
    """
    try:
        root = ET.fromstring(xhtml_bytes)
    except ET.ParseError:
        return None
    h1_texts: list[str] = []
    h2_texts: list[str] = []
    title_texts: list[str] = []
    for elem in root.iter("{http://www.w3.org/1999/xhtml}h1"):
        text = "".join(elem.itertext()).strip()
        if text:
            h1_texts.append(text)
    for elem in root.iter("{http://www.w3.org/1999/xhtml}h2"):
        text = "".join(elem.itertext()).strip()
        if text:
            h2_texts.append(text)
    for elem in root.iter("{http://www.w3.org/1999/xhtml}title"):
        text = "".join(elem.itertext()).strip()
        if text:
            title_texts.append(text)

    # h1 + h2 synthesis: when h1 matches dc_title and h2 holds a subtitle
    if dc_title and h1_texts and h2_texts:
        for h1_text in h1_texts:
            if h1_text.lower() == dc_title.lower():
                h2_text = _normalize_all_caps(h2_texts[0])
                return f"{h1_text}: {h2_text}"

    # Fallback: return the longest candidate across h1 / h2 / <title>
    candidates = h1_texts + h2_texts + title_texts
    if not candidates:
        return None
    return max(candidates, key=len)


def _split_subtitle(dc_title: str, full_candidate: str) -> tuple[str, str | None]:
    """If full_candidate contains dc_title as prefix + ':' or '—', split."""
    if not full_candidate.startswith(dc_title):
        return dc_title, None
    rest = full_candidate[len(dc_title):].lstrip()
    if rest and rest[0] in (":", "—", "-"):
        sub = rest[1:].strip()
        if sub:
            return dc_title, sub
    return dc_title, None


class EpubMetadataExtractor:
    """EPUB metadata extractor.

    `extract_metadata` always returns a BookMetadata; it does not raise on
    file-shape failures. See spec §7.
    """

    name = "epub_stdlib"

    def extract_metadata(self, path: Path, *, pages: int = 6) -> BookMetadata:
        # `pages` is ignored for EPUB (no concept of leading pages).
        del pages
        try:
            zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError) as exc:
            logger.warning("EPUB %s is not a valid zip: %s", path, exc)
            return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

        try:
            with zf:
                names = set(zf.namelist())

                # DRM detection
                if "META-INF/encryption.xml" in names:
                    try:
                        enc_bytes = zf.read("META-INF/encryption.xml")
                        if _ADOBE_DRM_NS.encode() in enc_bytes or _APPLE_DRM_NS.encode() in enc_bytes:
                            return BookMetadata(error=ErrorCode.DRM_PROTECTED)
                    except KeyError:
                        pass

                # Missing container.xml is malformed
                if "META-INF/container.xml" not in names:
                    return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

                # Parse container.xml to find OPF path
                container_xml = zf.read("META-INF/container.xml")
                opf_path = _find_opf_path(container_xml)
                if opf_path is None or opf_path not in names:
                    return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

                # Parse OPF
                try:
                    opf_root = ET.fromstring(zf.read(opf_path))
                except ET.ParseError as exc:
                    logger.warning("EPUB OPF parse failed for %s: %s", path, exc)
                    return BookMetadata(
                        error=ErrorCode.MALFORMED_EPUB,
                        warnings=[MetadataWarning(
                            code=WarningCode.INCOMPLETE_EXTRACTION, detail=str(exc),
                        )],
                    )

                # Find metadata element
                meta_elem = opf_root.find(f".//{{{_OPF_NS}}}metadata")
                if meta_elem is None:
                    return BookMetadata(error=ErrorCode.MALFORMED_EPUB)

                warnings: list[MetadataWarning] = []

                # Extract title
                dc_title = meta_elem.findtext(f"{{{_DC_NS}}}title")
                title = dc_title.strip() if dc_title else None

                # Extract publisher
                dc_publisher = meta_elem.findtext(f"{{{_DC_NS}}}publisher")
                publisher = dc_publisher.strip() if dc_publisher else None

                # Extract and normalise language
                dc_language = meta_elem.findtext(f"{{{_DC_NS}}}language")
                if dc_language:
                    norm, changed = _normalise_language(dc_language.strip())
                    language = norm
                    if changed:
                        warnings.append(MetadataWarning(
                            code=WarningCode.LANGUAGE_NORMALISED,
                            detail=f"{dc_language.strip()} -> {norm}",
                        ))
                else:
                    language = None

                # Extract creators
                creators = _extract_creators_from_opf(meta_elem, warnings)

                # Extract identifier
                identifier = _extract_identifier_from_opf(meta_elem)

                # Extract dates
                date, first_published = _extract_dates_from_opf(meta_elem)

                # Title-page xhtml fallback for subtitle
                subtitle: str | None = None
                if title is not None and ":" not in title and "—" not in title:
                    href = _find_title_page_href(opf_root, names)
                    if href is not None:
                        # Resolve href to a zip member path.
                        # _find_title_page_href may return either:
                        #   - a relative href from the OPF guide (e.g. 'title.xhtml')
                        #   - a full zip-member path from the name scan (e.g. 'OEBPS/Title.xhtml')
                        opf_dir = opf_path.rsplit("/", 1)[0] if "/" in opf_path else ""
                        if href in names:
                            # Already an absolute zip path (came from name scan)
                            candidate_path = href
                        elif opf_dir:
                            candidate_path = f"{opf_dir}/{href}"
                        else:
                            candidate_path = href
                        if candidate_path in names:
                            try:
                                xhtml_bytes = zf.read(candidate_path)
                                full_candidate = _parse_title_page_text(xhtml_bytes, dc_title=title)
                            except KeyError:
                                full_candidate = None
                            if full_candidate is not None and full_candidate != title:
                                t2, sub = _split_subtitle(title, full_candidate)
                                if sub is not None:
                                    title = t2
                                    subtitle = sub
                                    warnings.append(MetadataWarning(
                                        code=WarningCode.SUBTITLE_NOT_IN_OPF,
                                        detail=f"subtitle from title-page xhtml: {sub}",
                                    ))

                full_title = (f"{title}: {subtitle}" if subtitle else title) if title else None

                return BookMetadata(
                    identifier=identifier,
                    title=title,
                    subtitle=subtitle,
                    full_title=full_title,
                    publisher=publisher,
                    language=language,
                    creators=creators,
                    date=date,
                    first_published=first_published,
                    warnings=warnings,
                )
        except zipfile.BadZipFile as exc:
            logger.warning("EPUB %s zip read failed: %s", path, exc)
            return BookMetadata(
                error=ErrorCode.MALFORMED_EPUB,
                warnings=[MetadataWarning(
                    code=WarningCode.INCOMPLETE_EXTRACTION, detail=str(exc),
                )],
            )
