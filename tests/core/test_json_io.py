"""Atomic JSON reader/writer helpers."""

import json
from pathlib import Path

import pytest

from aa_auto_sdr.core import json_io


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    payload = {"a": 1, "b": [2, 3], "c": {"d": "x"}}
    target = tmp_path / "out.json"
    json_io.write_json(target, payload)
    assert json_io.read_json(target) == payload


def test_write_is_atomic_via_tmp_then_rename(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    json_io.write_json(target, {"x": 1})
    assert target.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_write_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "deep" / "nested" / "out.json"
    json_io.write_json(target, {"x": 1})
    assert target.exists()


def test_write_sorts_keys_for_diff_friendliness(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    json_io.write_json(target, {"b": 2, "a": 1, "c": 3})
    text = target.read_text()
    assert text.index('"a"') < text.index('"b"') < text.index('"c"')


def test_read_missing_raises_filenotfounderror(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        json_io.read_json(tmp_path / "missing.json")


def test_read_invalid_json_raises_jsondecodeerror(tmp_path: Path) -> None:
    target = tmp_path / "bad.json"
    target.write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        json_io.read_json(target)
