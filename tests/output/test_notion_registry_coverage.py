"""Targeted coverage for notion_registry edge cases.

Covers the unexpected-value coercion in `_normalize_entry`, the non-dict JSON
guard in `load_registry`, and the missing-rsid no-op in `drop_superseded`."""

from __future__ import annotations

import json
from pathlib import Path

from aa_auto_sdr.output import notion_registry as reg


def test_normalize_entry_coerces_unexpected_type() -> None:
    # Neither str nor dict → empty current/superseded.
    assert reg._normalize_entry(123) == {"current": "", "superseded": []}


def test_load_registry_non_dict_json_returns_empty(tmp_path: Path) -> None:
    p = tmp_path / reg.REGISTRY_FILENAME
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")  # valid JSON, wrong shape
    assert reg.load_registry(p) == {}


def test_drop_superseded_missing_rsid_is_noop(tmp_path: Path) -> None:
    p = tmp_path / reg.REGISTRY_FILENAME
    reg.store_page_id(p, "rs1", "page_a")
    reg.drop_superseded(p, "missing", "page_x")  # no entry → early return
    assert reg.load_registry(p)["rs1"]["current"] == "page_a"
