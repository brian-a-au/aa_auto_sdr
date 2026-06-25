"""Targeted coverage for the CSV writer helpers.

Covers the atomic-write cleanup-on-failure path and the empty-input branch of
`_component_rows`."""

from __future__ import annotations

from pathlib import Path

import pytest

import aa_auto_sdr.output.writers.csv as csvmod
from aa_auto_sdr.output.writers.csv import _component_rows


def test_atomic_write_text_cleans_up_tmp_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(csvmod.os, "replace", _boom)
    target = tmp_path / "out.csv"
    with pytest.raises(OSError, match="replace failed"):
        csvmod._atomic_write_text(target, "data", encoding="utf-8")
    # The target is never created and the temp file is unlinked.
    assert not target.exists()
    leftover = [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftover == []


def test_component_rows_empty_returns_empty_pair() -> None:
    assert _component_rows([]) == ([], [])
