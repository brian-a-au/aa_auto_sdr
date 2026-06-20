"""Tests for Notion page ID registry."""

from __future__ import annotations

import json
from pathlib import Path

from aa_auto_sdr.output import notion_registry as reg
from aa_auto_sdr.output.notion_registry import (
    REGISTRY_FILENAME,
    get_registry_path,
    load_registry,
    lookup_page_id,
    save_registry,
    store_page_id,
)


def test_registry_filename_constant():
    assert REGISTRY_FILENAME == ".notion_pages.json"


def test_get_registry_path(tmp_path):
    assert get_registry_path(tmp_path) == tmp_path / REGISTRY_FILENAME


def test_load_registry_missing_file_returns_empty(tmp_path):
    assert load_registry(tmp_path / "nope.json") == {}


def test_load_registry_reads_existing(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    p.write_text(json.dumps({"examplersid1": "page-abc"}))
    # flat shape is upgraded to the object shape on load
    assert load_registry(p) == {"examplersid1": {"current": "page-abc", "superseded": []}}


def test_load_registry_malformed_returns_empty(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    p.write_text("{not valid json}")
    assert load_registry(p) == {}


def test_load_registry_non_utf8_returns_empty(tmp_path):
    # A registry file with non-UTF-8 bytes (e.g. corrupted on disk) raises
    # UnicodeDecodeError on read_text(encoding="utf-8"). Treat the same as
    # any other malformed-registry case: return {} so the next run starts
    # clean rather than crashing the publish.
    p = tmp_path / REGISTRY_FILENAME
    p.write_bytes(b"\xff\xfe\xfd not utf-8")
    assert load_registry(p) == {}


def test_load_registry_os_error_returns_empty(tmp_path, monkeypatch):
    # Simulate the registry file existing but being unreadable (permissions,
    # transient FS error). load_registry must swallow OSError and return {}
    # so the next run cleanly starts a new registry rather than crashing.
    p = tmp_path / REGISTRY_FILENAME
    p.write_text("{}")

    def _raise_oserror(self, *args, **kwargs):
        raise OSError("simulated read failure")

    monkeypatch.setattr("pathlib.Path.read_text", _raise_oserror)
    assert load_registry(p) == {}


def test_save_registry_writes_json_atomically(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    save_registry(p, {"examplersid2": {"current": "page-def", "superseded": []}})
    assert json.loads(p.read_text()) == {"examplersid2": {"current": "page-def", "superseded": []}}


def test_lookup_page_id_found(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    p.write_text(json.dumps({"a": "page-a", "b": "page-b"}))
    assert lookup_page_id(p, "a") == "page-a"


def test_lookup_page_id_missing_key(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    p.write_text(json.dumps({"a": "page-a"}))
    assert lookup_page_id(p, "z") is None


def test_lookup_page_id_missing_registry(tmp_path):
    assert lookup_page_id(tmp_path / "nope.json", "a") is None


def test_store_page_id_creates_entry(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    store_page_id(p, "examplersid1", "page-abc")
    # on-disk shape is always the object shape
    assert json.loads(p.read_text())["examplersid1"] == {"current": "page-abc", "superseded": []}


def test_store_page_id_updates_existing_entry(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    p.write_text(json.dumps({"examplersid1": "old"}))
    store_page_id(p, "examplersid1", "new")
    # old id is tombstoned, new id is current
    assert json.loads(p.read_text())["examplersid1"] == {"current": "new", "superseded": ["old"]}


def test_store_page_id_preserves_other_entries(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    p.write_text(json.dumps({"keep": "keeper"}))
    store_page_id(p, "new", "newer")
    data = json.loads(p.read_text())
    assert data == {"keep": {"current": "keeper", "superseded": []}, "new": {"current": "newer", "superseded": []}}


# ---------------------------------------------------------------------------
# Registry v2 shape, tombstones, and lock
# ---------------------------------------------------------------------------


def test_load_upgrades_flat_shape(tmp_path: Path):
    p = tmp_path / reg.REGISTRY_FILENAME
    p.write_text(json.dumps({"rs1": "page_a"}), encoding="utf-8")
    loaded = reg.load_registry(p)
    assert loaded == {"rs1": {"current": "page_a", "superseded": []}}


def test_load_object_shape_roundtrip(tmp_path: Path):
    p = tmp_path / reg.REGISTRY_FILENAME
    data = {"rs1": {"current": "page_a", "superseded": ["old1"]}}
    p.write_text(json.dumps(data), encoding="utf-8")
    assert reg.load_registry(p) == data


def test_store_page_id_tombstones_old_on_change(tmp_path: Path):
    p = tmp_path / reg.REGISTRY_FILENAME
    reg.store_page_id(p, "rs1", "page_a")
    reg.store_page_id(p, "rs1", "page_b")  # repoint → tombstone page_a
    loaded = reg.load_registry(p)
    assert loaded["rs1"]["current"] == "page_b"
    assert loaded["rs1"]["superseded"] == ["page_a"]


def test_store_page_id_same_id_no_tombstone(tmp_path: Path):
    p = tmp_path / reg.REGISTRY_FILENAME
    reg.store_page_id(p, "rs1", "page_a")
    reg.store_page_id(p, "rs1", "page_a")  # in-place update → no tombstone
    assert reg.load_registry(p)["rs1"]["superseded"] == []


def test_lookup_page_id_returns_current(tmp_path: Path):
    p = tmp_path / reg.REGISTRY_FILENAME
    reg.store_page_id(p, "rs1", "page_a")
    assert reg.lookup_page_id(p, "rs1") == "page_a"
    assert reg.lookup_page_id(p, "missing") is None


def test_collect_and_drop_superseded(tmp_path: Path):
    p = tmp_path / reg.REGISTRY_FILENAME
    reg.store_page_id(p, "rs1", "page_a")
    reg.store_page_id(p, "rs1", "page_b")
    reg.store_page_id(p, "rs2", "page_c")
    reg.store_page_id(p, "rs2", "page_d")
    orphans = reg.collect_superseded(reg.load_registry(p))
    assert sorted(orphans) == [("rs1", "page_a"), ("rs2", "page_c")]
    reg.drop_superseded(p, "rs1", "page_a")
    assert reg.load_registry(p)["rs1"]["superseded"] == []
