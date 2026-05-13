"""MetadataExtractor Protocol — see docs/superpowers/specs/2026-05-13-extract-metadata-design.md §2.

Each format gets one extractor. Backends remain separate (in `backends/`)
and are used for the heavyweight IR path; metadata extractors are
lightweight, no caching, no Docling.
"""
from __future__ import annotations
