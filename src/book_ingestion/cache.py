"""Content-hash-keyed disk cache.

The cache key is the sha256 of the file *content*, not its path. Each cached
entry is stored under `~/.cache/book-ingestion/<sha256>/`. A `meta.json` records
the `schema_version`; mismatches invalidate the entry transparently.

The cache is opaque to callers: `cache_paths.*` fields in the IR are convenience
pointers, but consumers must never write into the cache themselves.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from book_ingestion.ir import SCHEMA_VERSION

logger = logging.getLogger(__name__)

_CHUNK = 1 << 20  # 1 MiB


def sha256_of_file(path: Path) -> str:
    """Streaming sha256 of file content."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def default_cache_root() -> Path:
    return Path.home() / ".cache" / "book-ingestion"


class Cache:
    """Disk cache scoped to a content-hash directory."""

    def __init__(self, root: Path | None = None, schema_version: str = SCHEMA_VERSION) -> None:
        self.root = root if root is not None else default_cache_root()
        self.schema_version = schema_version
        self.root.mkdir(parents=True, exist_ok=True)

    def dir_for(self, path: Path) -> Path:
        digest = sha256_of_file(path)
        return self.root / digest

    def _meta_path(self, path: Path) -> Path:
        return self.dir_for(path) / "meta.json"

    def _ensure_meta(self, path: Path) -> None:
        """Write meta.json if absent. If present with mismatched schema, leave it
        as-is (read() will detect the mismatch and invalidate)."""
        d = self.dir_for(path)
        d.mkdir(parents=True, exist_ok=True)
        meta_path = self._meta_path(path)
        if not meta_path.exists():
            meta = {
                "origin_path": str(path),
                "size_bytes": path.stat().st_size,
                "schema_version": self.schema_version,
                "created_at": datetime.now(UTC).isoformat(),
            }
            meta_path.write_text(json.dumps(meta, indent=2))

    def _entry_valid(self, path: Path) -> bool:
        meta_path = self._meta_path(path)
        if not meta_path.exists():
            return False
        try:
            meta = json.loads(meta_path.read_text())
        except json.JSONDecodeError:
            return False
        return bool(meta.get("schema_version") == self.schema_version)

    def write(self, path: Path, name: str, payload: Any) -> Path:
        """Write a JSON payload to <cache>/<sha256>/<name>. Creates meta.json if missing."""
        self._ensure_meta(path)
        target = self.dir_for(path) / name
        target.write_text(json.dumps(payload, indent=2))
        return target

    def read(self, path: Path, name: str) -> Any | None:
        """Return the cached JSON payload or None on miss / invalidation."""
        if not self._entry_valid(path):
            if self._meta_path(path).exists():
                logger.info(
                    "cache entry schema-version mismatch; invalidating %s",
                    self.dir_for(path),
                )
            return None
        target = self.dir_for(path) / name
        if not target.exists():
            return None
        try:
            return json.loads(target.read_text())
        except json.JSONDecodeError:
            return None

    def clear(self, path: Path) -> None:
        """Remove the cache directory for a single file. No-op if absent."""
        d = self.dir_for(path)
        if d.exists():
            for p in d.iterdir():
                p.unlink()
            d.rmdir()
