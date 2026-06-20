"""Local page ID registry for Notion integration.

Maps each RSID to its current Notion page id and any superseded ids
(pages abandoned by --notion-force-new). Registry file:
``.notion_pages.json`` in the output directory (or CWD if ``--output-dir``
is not set). The per-RSID value is ``{"current": str, "superseded": [str]}``.
The old flat shape ``{rsid: page_id}`` still loads.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from aa_auto_sdr.core.json_io import write_json

REGISTRY_FILENAME = ".notion_pages.json"

# Batch workers are threads in one process sharing one registry file
# (pipeline/workers.py uses ThreadPoolExecutor). This lock serializes the
# read-modify-write so concurrent --workers writes cannot lose entries.
_REGISTRY_LOCK = threading.Lock()

_LOAD_ERRORS: tuple[type[Exception], ...] = (json.JSONDecodeError, OSError, UnicodeDecodeError)


def get_registry_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / REGISTRY_FILENAME


def _normalize_entry(value: object) -> dict:
    """Coerce either shape into ``{"current": str, "superseded": [str]}``."""
    if isinstance(value, str):
        return {"current": value, "superseded": []}
    if isinstance(value, dict):
        current = value.get("current")
        superseded = value.get("superseded")
        return {
            "current": current if isinstance(current, str) else "",
            "superseded": [s for s in superseded if isinstance(s, str)] if isinstance(superseded, list) else [],
        }
    return {"current": "", "superseded": []}


def load_registry(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except _LOAD_ERRORS:
        return {}
    if not isinstance(data, dict):
        return {}
    return {rsid: _normalize_entry(val) for rsid, val in data.items()}


def save_registry(path: Path, registry: dict[str, dict]) -> None:
    # Sort superseded lists for stable, git-friendly diffs. write_json sorts keys.
    normalized = {
        rsid: {"current": entry.get("current", ""), "superseded": sorted(entry.get("superseded", []))}
        for rsid, entry in registry.items()
    }
    write_json(path, normalized)


def lookup_page_id(registry_path: Path, rsid: str) -> str | None:
    entry = load_registry(registry_path).get(rsid)
    if not entry:
        return None
    return entry.get("current") or None


def store_page_id(registry_path: Path, rsid: str, page_id: str) -> None:
    with _REGISTRY_LOCK:
        registry = load_registry(registry_path)
        entry = registry.get(rsid) or {"current": "", "superseded": []}
        old = entry.get("current") or ""
        if old and old != page_id and old not in entry["superseded"]:
            entry["superseded"].append(old)
        entry["current"] = page_id
        registry[rsid] = entry
        save_registry(registry_path, registry)


def collect_superseded(registry: dict[str, dict]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for rsid, entry in registry.items():
        out.extend((rsid, page_id) for page_id in entry.get("superseded", []))
    return out


def drop_superseded(registry_path: Path, rsid: str, page_id: str) -> None:
    with _REGISTRY_LOCK:
        registry = load_registry(registry_path)
        entry = registry.get(rsid)
        if not entry:
            return
        entry["superseded"] = [s for s in entry.get("superseded", []) if s != page_id]
        registry[rsid] = entry
        save_registry(registry_path, registry)
