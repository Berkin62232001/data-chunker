"""Constrain document and project paths to their configured storage root."""
import re
from pathlib import Path


class UnsafeStoragePath(ValueError):
    pass


def storage_path(root: Path, identifier: str, *parts: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", identifier):
        raise UnsafeStoragePath("Invalid document or project identifier.")
    base = root.resolve()
    path = root / identifier
    for part in parts:
        path = path / part
    resolved = path.resolve()
    if base not in resolved.parents:
        raise UnsafeStoragePath("Storage path is outside its configured root.")
    return path
