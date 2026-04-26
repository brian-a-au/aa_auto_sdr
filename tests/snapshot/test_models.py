"""snapshot/models.py — DiffReport / ComponentDiff / FieldDelta dataclasses."""

from dataclasses import FrozenInstanceError

import pytest

from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
    FieldDelta,
    ModifiedItem,
)


def test_field_delta_construction() -> None:
    fd = FieldDelta(field="name", before="Old", after="New")
    assert fd.field == "name"
    assert fd.before == "Old"
    assert fd.after == "New"


def test_field_delta_is_frozen() -> None:
    fd = FieldDelta(field="x", before=1, after=2)
    with pytest.raises(FrozenInstanceError):
        fd.field = "y"  # type: ignore[misc]


def test_added_removed_item_construction() -> None:
    a = AddedRemovedItem(id="evar99", name="Mobile Operator")
    assert a.id == "evar99"
    assert a.name == "Mobile Operator"


def test_modified_item_construction() -> None:
    m = ModifiedItem(
        id="evar15",
        name="Page Type",
        deltas=[FieldDelta(field="type", before="string", after="enum")],
    )
    assert m.id == "evar15"
    assert len(m.deltas) == 1


def test_component_diff_construction() -> None:
    cd = ComponentDiff(
        component_type="dimensions",
        added=[AddedRemovedItem(id="evar99", name="Mobile Operator")],
        removed=[],
        modified=[],
        unchanged_count=124,
    )
    assert cd.component_type == "dimensions"
    assert cd.unchanged_count == 124
    assert cd.added[0].id == "evar99"


def test_component_diff_is_frozen() -> None:
    cd = ComponentDiff(
        component_type="metrics",
        added=[],
        removed=[],
        modified=[],
        unchanged_count=0,
    )
    with pytest.raises(FrozenInstanceError):
        cd.component_type = "x"  # type: ignore[misc]


def test_diff_report_construction() -> None:
    dr = DiffReport(
        a_rsid="demo.prod",
        b_rsid="demo.prod",
        a_captured_at="2026-04-20T10:00:00+00:00",
        b_captured_at="2026-04-26T17:29:01+00:00",
        a_tool_version="0.5.0",
        b_tool_version="0.7.0",
        report_suite_deltas=[],
        components=[],
        rsid_mismatch=False,
    )
    assert dr.a_rsid == "demo.prod"
    assert dr.rsid_mismatch is False


def test_diff_report_rsid_mismatch_flag() -> None:
    dr = DiffReport(
        a_rsid="demo.prod",
        b_rsid="demo.staging",
        a_captured_at="x",
        b_captured_at="y",
        a_tool_version="0.5.0",
        b_tool_version="0.7.0",
        report_suite_deltas=[],
        components=[],
        rsid_mismatch=True,
    )
    assert dr.rsid_mismatch is True
