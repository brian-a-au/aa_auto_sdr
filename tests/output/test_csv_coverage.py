"""Targeted coverage for the CSV writer helpers.

Covers the empty-input branch of `_component_rows`. Staged publication is
covered in test_csv_manifest.py."""

from __future__ import annotations

from aa_auto_sdr.output.writers.csv import _component_rows


def test_component_rows_empty_returns_model_headers_and_no_rows() -> None:
    headers, rows = _component_rows("dimensions", [])
    assert headers[0] == "id"
    assert rows == []
    seg_headers, _ = _component_rows("segments", [])
    assert seg_headers[-3:] == ["definition_summary", "metric_references", "segment_references"]
