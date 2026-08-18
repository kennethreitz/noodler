"""Persistence for the application-level Open Recent list."""

import json
from pathlib import Path


def recent_documents(store: Path, limit: int) -> list[Path]:
    """Return existing documents from a recent-file store, newest first."""
    try:
        listed = json.loads(store.read_text())
    except (OSError, ValueError):
        return []
    found: list[Path] = []
    for entry in listed if isinstance(listed, list) else []:
        try:
            path = Path(str(entry))
        except (TypeError, ValueError):
            continue
        if path.is_file() and path not in found:
            found.append(path)
    return found[:limit]


def remember_recent(path: Path, store: Path, limit: int) -> None:
    """Put a document at the top of a recent-file store."""
    resolved = path.resolve()
    recent = [resolved] + [
        candidate
        for candidate in recent_documents(store, limit)
        if candidate != resolved
    ]
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps([str(candidate) for candidate in recent[:limit]], indent=2))
