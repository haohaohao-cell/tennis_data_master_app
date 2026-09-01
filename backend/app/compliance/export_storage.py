"""Protected export-file storage boundary.

Only the local test-file provider is implemented. Production object storage is
an explicit configuration contract, not an implicit filesystem fallback.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol
import uuid

from backend.app.core.config import settings


class ExportStorage(Protocol):
    def put_export(self, request_id: str, content: bytes) -> str: ...
    def open_export(self, key: str) -> Path: ...
    def exists_export(self, key: str) -> bool: ...
    def delete_export(self, key: str) -> bool: ...


class TestFileExportStorage:
    """Atomically store exports under one private root using opaque relative keys."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        candidate = Path(key)
        if candidate.name != key or not key.endswith(".json"):
            raise ValueError("invalid export storage key")
        path = (self._root / candidate).resolve()
        if self._root not in path.parents:
            raise ValueError("invalid export storage key")
        return path

    def put_export(self, request_id: str, content: bytes) -> str:
        key = f"{request_id}.json"
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
        try:
            temporary.write_bytes(content)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
        return key

    def open_export(self, key: str) -> Path:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path

    def exists_export(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except ValueError:
            return False

    def delete_export(self, key: str) -> bool:
        try:
            path = self._path(key)
        except ValueError:
            return False
        if not path.is_file():
            return False
        path.unlink()
        return True


def get_export_storage() -> ExportStorage:
    """Resolve the configured provider without silently substituting test storage."""
    if settings.export_storage_provider == "test_file":
        return TestFileExportStorage(settings.export_storage_dir)
    if settings.export_storage_provider == "external_contract":
        raise RuntimeError("External export storage is configured but not implemented.")
    raise RuntimeError("Unsupported export storage provider.")
