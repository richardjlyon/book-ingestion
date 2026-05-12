"""Backend registry. v1 exposes the pdf backend only."""
from __future__ import annotations

from book_ingestion.backends.base import Backend, Context

# Populated lazily by api.py to avoid eager imports of heavy deps (Docling).
__all__ = ["Backend", "Context"]
