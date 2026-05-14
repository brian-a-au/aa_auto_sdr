"""Tests for Notion page ID registry."""

from __future__ import annotations

import json

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
    assert load_registry(p) == {"examplersid1": "page-abc"}


def test_load_registry_malformed_returns_empty(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    p.write_text("{not valid json}")
    assert load_registry(p) == {}


def test_save_registry_writes_json_atomically(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    save_registry(p, {"examplersid2": "page-def"})
    assert json.loads(p.read_text()) == {"examplersid2": "page-def"}


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
    assert json.loads(p.read_text())["examplersid1"] == "page-abc"


def test_store_page_id_updates_existing_entry(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    p.write_text(json.dumps({"examplersid1": "old"}))
    store_page_id(p, "examplersid1", "new")
    assert json.loads(p.read_text())["examplersid1"] == "new"


def test_store_page_id_preserves_other_entries(tmp_path):
    p = tmp_path / REGISTRY_FILENAME
    p.write_text(json.dumps({"keep": "keeper"}))
    store_page_id(p, "new", "newer")
    data = json.loads(p.read_text())
    assert data == {"keep": "keeper", "new": "newer"}
