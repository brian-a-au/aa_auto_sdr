"""Targeted coverage for the CSV writer helpers.

Covers the empty-input branch of `_component_rows`. Staged publication is
covered in test_csv_manifest.py."""

from __future__ import annotations

from aa_auto_sdr.output.writers.csv import _component_rows


def test_component_rows_empty_returns_empty_pair() -> None:
    assert _component_rows([]) == ([], [])
