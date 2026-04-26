"""snapshot/comparator.py — pure diff algorithm with §5.1 normalization."""

from __future__ import annotations

from typing import Any

from aa_auto_sdr.snapshot.comparator import compare
from aa_auto_sdr.snapshot.models import DiffReport


def _envelope(
    rsid: str = "demo.prod",
    *,
    captured_at: str = "2026-04-26T17:29:01+00:00",
    tool_version: str = "0.7.0",
    rs_overrides: dict | None = None,
    dims: list | None = None,
    metrics: list | None = None,
    segments: list | None = None,
    calculated_metrics: list | None = None,
    vrses: list | None = None,
    classifications: list | None = None,
) -> dict[str, Any]:
    return {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": rsid,
        "captured_at": captured_at,
        "tool_version": tool_version,
        "components": {
            "report_suite": {
                "rsid": rsid,
                "name": rsid,
                "timezone": "UTC",
                "currency": "USD",
                "parent_rsid": None,
                **(rs_overrides or {}),
            },
            "dimensions": dims or [],
            "metrics": metrics or [],
            "segments": segments or [],
            "calculated_metrics": calculated_metrics or [],
            "virtual_report_suites": vrses or [],
            "classifications": classifications or [],
        },
    }


def _dim(id: str, name: str, **extra) -> dict:
    return {
        "id": id,
        "name": name,
        "type": "string",
        "category": "Custom",
        "parent": "",
        "pathable": False,
        "description": None,
        "tags": [],
        "extra": {},
        **extra,
    }


def test_compare_returns_diff_report() -> None:
    a = _envelope()
    b = _envelope()
    report = compare(a, b)
    assert isinstance(report, DiffReport)


def test_compare_unchanged_zero_deltas() -> None:
    a = _envelope(dims=[_dim("evar1", "User ID")])
    b = _envelope(dims=[_dim("evar1", "User ID")])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert dim_diff.added == []
    assert dim_diff.removed == []
    assert dim_diff.modified == []
    assert dim_diff.unchanged_count == 1


def test_compare_added_component() -> None:
    a = _envelope(dims=[_dim("evar1", "User ID")])
    b = _envelope(dims=[_dim("evar1", "User ID"), _dim("evar2", "Plan")])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert [x.id for x in dim_diff.added] == ["evar2"]
    assert dim_diff.unchanged_count == 1


def test_compare_removed_component() -> None:
    a = _envelope(dims=[_dim("evar1", "User ID"), _dim("evar2", "Plan")])
    b = _envelope(dims=[_dim("evar1", "User ID")])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert [x.id for x in dim_diff.removed] == ["evar2"]


def test_compare_modified_component_field_delta() -> None:
    a = _envelope(dims=[_dim("evar1", "User ID", type="string")])
    b = _envelope(dims=[_dim("evar1", "User ID", type="enum")])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert len(dim_diff.modified) == 1
    mod = dim_diff.modified[0]
    assert mod.id == "evar1"
    fields = {d.field for d in mod.deltas}
    assert "type" in fields
    type_delta = next(d for d in mod.deltas if d.field == "type")
    assert type_delta.before == "string"
    assert type_delta.after == "enum"


def test_compare_identity_by_id_not_name() -> None:
    """A name change is a modification, not add+remove (master spec invariant)."""
    a = _envelope(dims=[_dim("evar1", "User ID")])
    b = _envelope(dims=[_dim("evar1", "Customer ID")])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert dim_diff.added == []
    assert dim_diff.removed == []
    assert len(dim_diff.modified) == 1


def test_compare_normalization_treats_none_and_empty_string_as_equal() -> None:
    a = _envelope(dims=[_dim("evar1", "User ID", description=None)])
    b = _envelope(dims=[_dim("evar1", "User ID", description="")])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert dim_diff.modified == []
    assert dim_diff.unchanged_count == 1


def test_compare_normalization_strips_string_whitespace() -> None:
    a = _envelope(dims=[_dim("evar1", "User ID", description="hello")])
    b = _envelope(dims=[_dim("evar1", "User ID", description="  hello  ")])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert dim_diff.modified == []


def test_compare_normalization_tags_are_order_insensitive() -> None:
    a = _envelope(dims=[_dim("evar1", "User ID", tags=["A", "B"])])
    b = _envelope(dims=[_dim("evar1", "User ID", tags=["B", "A"])])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert dim_diff.modified == []


def test_compare_report_suite_field_delta() -> None:
    a = _envelope()
    b = _envelope(rs_overrides={"name": "Demo Production v2"})
    report = compare(a, b)
    assert any(d.field == "name" for d in report.report_suite_deltas)


def test_compare_rsid_mismatch_flag_set() -> None:
    a = _envelope(rsid="demo.prod")
    b = _envelope(rsid="demo.staging")
    report = compare(a, b)
    assert report.rsid_mismatch is True


def test_compare_rsid_match_flag_not_set() -> None:
    a = _envelope(rsid="demo.prod")
    b = _envelope(rsid="demo.prod")
    report = compare(a, b)
    assert report.rsid_mismatch is False


def test_compare_components_in_canonical_order() -> None:
    """All six component types appear in the report, in stable order."""
    a = _envelope()
    b = _envelope()
    report = compare(a, b)
    types = [c.component_type for c in report.components]
    assert types == [
        "dimensions",
        "metrics",
        "segments",
        "calculated_metrics",
        "virtual_report_suites",
        "classifications",
    ]


def test_compare_added_and_modified_lists_sorted_by_id() -> None:
    a = _envelope(dims=[_dim("a", "A")])
    b = _envelope(dims=[_dim("a", "A"), _dim("z", "Z"), _dim("m", "M")])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert [x.id for x in dim_diff.added] == ["m", "z"]
