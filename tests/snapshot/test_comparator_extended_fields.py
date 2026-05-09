"""--extended-fields toggles a default suppression set in the comparator.

Default: noisy fields (description, tags, category, etc.) suppressed.
With extended_fields=True: those fields included.

See spec §3.4.
"""

from __future__ import annotations

from aa_auto_sdr.snapshot.comparator import compare


def _envelope(*, dimensions: list[dict] | None = None) -> dict:
    return {
        "schema": "aa-sdr-snapshot/v3",
        "rsid": "rs1",
        "captured_at": "2026-05-09T00:00:00+00:00",
        "tool_version": "1.9.0",
        "degraded_components": [],
        "partial_components": {},
        "quality": None,
        "components": {
            "report_suite": {"rsid": "rs1", "name": "Test"},
            "dimensions": dimensions or [],
            "metrics": [],
            "segments": [],
            "calculated_metrics": [],
            "virtual_report_suites": [],
            "classifications": [],
        },
    }


def _dim(id_: str, name: str, **extra) -> dict:
    base = {
        "id": id_,
        "name": name,
        "type": "string",
        "category": None,
        "parent": "",
        "pathable": False,
        "description": None,
        "tags": [],
    }
    base.update(extra)
    return base


def test_default_suppresses_description_field() -> None:
    """Description differs but extended_fields=False → not in diff."""
    a = _envelope(dimensions=[_dim("evar1", "Foo", description="old desc")])
    b = _envelope(dimensions=[_dim("evar1", "Foo", description="new desc")])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    # core fields (id, name, type) match → no modified entries
    assert dim_diff.modified == []


def test_extended_compares_description_field() -> None:
    a = _envelope(dimensions=[_dim("evar1", "Foo", description="old desc")])
    b = _envelope(dimensions=[_dim("evar1", "Foo", description="new desc")])
    report = compare(a, b, extended_fields=True)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert len(dim_diff.modified) == 1
    field_names = {d.field for d in dim_diff.modified[0].deltas}
    assert "description" in field_names


def test_default_suppresses_tags_field() -> None:
    a = _envelope(dimensions=[_dim("evar1", "Foo", tags=["v1"])])
    b = _envelope(dimensions=[_dim("evar1", "Foo", tags=["v2"])])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert dim_diff.modified == []


def test_extended_compares_tags_field() -> None:
    a = _envelope(dimensions=[_dim("evar1", "Foo", tags=["v1"])])
    b = _envelope(dimensions=[_dim("evar1", "Foo", tags=["v2"])])
    report = compare(a, b, extended_fields=True)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert len(dim_diff.modified) == 1


def test_default_still_compares_core_fields() -> None:
    """`name` must still diff at default — it's a core field, not extended."""
    a = _envelope(dimensions=[_dim("evar1", "Foo")])
    b = _envelope(dimensions=[_dim("evar1", "Bar")])
    report = compare(a, b)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert len(dim_diff.modified) == 1


def test_extended_fields_default_false_preserves_pre_v1_9_behavior() -> None:
    """Regression lock: extended_fields=False suppresses description/tags etc."""
    a = _envelope(dimensions=[_dim("evar1", "Foo", description="old")])
    b = _envelope(dimensions=[_dim("evar1", "Foo", description="new")])
    report = compare(a, b, extended_fields=False)
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert dim_diff.modified == []


def test_user_ignore_fields_combines_with_extended_default() -> None:
    """User-supplied --ignore-fields adds to the default suppression."""
    a = _envelope(dimensions=[_dim("evar1", "Foo", category="X")])
    b = _envelope(dimensions=[_dim("evar1", "Foo", category="Y")])
    # User explicitly ignores `category`; extended_fields default is False
    # (so `category` would be suppressed anyway, but verify combined behavior)
    report = compare(a, b, ignore_fields=frozenset({"category"}))
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert dim_diff.modified == []


def test_extended_with_user_ignore_fields_user_wins() -> None:
    """User-supplied --ignore-fields wins even when extended_fields=True."""
    a = _envelope(dimensions=[_dim("evar1", "Foo", description="old")])
    b = _envelope(dimensions=[_dim("evar1", "Foo", description="new")])
    report = compare(
        a,
        b,
        ignore_fields=frozenset({"description"}),
        extended_fields=True,
    )
    dim_diff = next(c for c in report.components if c.component_type == "dimensions")
    assert dim_diff.modified == []
