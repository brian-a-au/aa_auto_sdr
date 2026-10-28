"""Malformed component rows are a typed snapshot error, not a traceback.

`validate_envelope` used to check only that rows were dicts, so a row with
no `id` reached `comparator._diff_component_list` and raised a bare
`KeyError` (exit 1). Duplicate ids collapsed silently and skewed
`unchanged_count`. A missing optional `components.report_suite` block raised
`KeyError` in `compare` even though the schema treats it as optional.
"""

from __future__ import annotations

from typing import Any

import pytest

from aa_auto_sdr.core.exceptions import SnapshotCorruptError
from aa_auto_sdr.snapshot.comparator import compare
from aa_auto_sdr.snapshot.schema import validate_envelope


def _envelope(*, dims: list | None = None, with_report_suite: bool = True) -> dict[str, Any]:
    components: dict[str, Any] = {
        "dimensions": dims if dims is not None else [],
        "metrics": [],
        "segments": [],
        "calculated_metrics": [],
        "virtual_report_suites": [],
        "classifications": [],
    }
    if with_report_suite:
        components["report_suite"] = {
            "rsid": "demo.prod",
            "name": "Demo",
            "timezone": "UTC",
            "currency": "USD",
            "parent_rsid": None,
        }
    return {
        "schema": "aa-sdr-snapshot/v4",
        "rsid": "demo.prod",
        "captured_at": "2026-04-26T17:29:01+00:00",
        "tool_version": "1.24.3",
        "degraded_components": [],
        "partial_components": {},
        "quality": None,
        "collected_components": [
            "calculated_metrics",
            "classifications",
            "dimensions",
            "metrics",
            "segments",
            "virtual_report_suites",
        ],
        "components": components,
    }


def _dim(ident: str | None, name: str) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "type": "string"}
    if ident is not None:
        row["id"] = ident
    return row


def test_row_without_id_is_corrupt() -> None:
    env = _envelope(dims=[_dim(None, "no id")])
    with pytest.raises(SnapshotCorruptError, match=r"components\.dimensions\[0\].*id"):
        validate_envelope(env)


def test_row_with_non_string_id_is_corrupt() -> None:
    env = _envelope(dims=[{"id": 17, "name": "numeric id"}])
    with pytest.raises(SnapshotCorruptError, match=r"components\.dimensions\[0\].*id"):
        validate_envelope(env)


def test_row_with_blank_id_is_corrupt() -> None:
    env = _envelope(dims=[_dim("   ", "blank id")])
    with pytest.raises(SnapshotCorruptError, match=r"components\.dimensions\[0\].*id"):
        validate_envelope(env)


def test_duplicate_ids_in_one_family_are_corrupt() -> None:
    env = _envelope(dims=[_dim("evar1", "First"), _dim("evar1", "Second")])
    with pytest.raises(SnapshotCorruptError, match="duplicate component id"):
        validate_envelope(env)


def test_same_id_across_families_is_accepted() -> None:
    env = _envelope(dims=[_dim("shared", "Dimension")])
    env["components"]["metrics"] = [_dim("shared", "Metric")]
    validate_envelope(env)  # ids are only unique within a family


def test_well_formed_rows_still_validate() -> None:
    env = _envelope(dims=[_dim("evar1", "eVar 1"), _dim("evar2", "eVar 2")])
    validate_envelope(env)


def test_compare_tolerates_missing_report_suite_block() -> None:
    """The schema calls `components.report_suite` optional and
    `sdr/rebuild.py` falls back to the envelope rsid, so `compare` must not
    raise when one side omits it."""
    a = _envelope(with_report_suite=False)
    b = _envelope()
    report = compare(a, b)
    assert report.settings_changes == len(report.report_suite_deltas)
    # `rsid` is an identity field and `parent_rsid` is None on the present
    # side, which normalizes equal to the absent side.
    assert {d.field for d in report.report_suite_deltas} == {"name", "timezone", "currency"}


def test_compare_tolerates_missing_report_suite_on_both_sides() -> None:
    report = compare(_envelope(with_report_suite=False), _envelope(with_report_suite=False))
    assert report.report_suite_deltas == []
    assert report.settings_changes == 0
