"""Local page ID registry for Notion integration.

Maps RSIDs to Notion page IDs so re-runs update existing pages rather
than accumulating duplicates. Registry file: ``.notion_pages.json`` in
the output directory (or CWD if ``--output-dir`` is not set).
"""

from __future__ import annotations

import json
from pathlib import Path

from aa_auto_sdr.core.json_io import write_json

REGISTRY_FILENAME = ".notion_pages.json"


def get_registry_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / REGISTRY_FILENAME


_LOAD_ERRORS: tuple[type[Exception], ...] = (json.JSONDecodeError, OSError, UnicodeDecodeError)


def load_registry(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except _LOAD_ERRORS:
        return {}
    return data if isinstance(data, dict) else {}


def save_registry(path: Path, registry: dict[str, str]) -> None:
    write_json(path, registry)


def lookup_page_id(registry_path: Path, rsid: str) -> str | None:
    return load_registry(registry_path).get(rsid)


def store_page_id(registry_path: Path, rsid: str, page_id: str) -> None:
    registry = load_registry(registry_path)
    registry[rsid] = page_id
    save_registry(registry_path, registry)
