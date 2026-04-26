"""output/diff_renderers/json.py — DiffReport → sorted-key JSON string."""

from __future__ import annotations

import json

from aa_auto_sdr.output.diff_renderers.json import render_json
from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
    FieldDelta,
    ModifiedItem,
)


def _stub_report() -> DiffReport:
    return DiffReport(
        a_rsid="demo.prod",
        b_rsid="demo.prod",
        a_captured_at="2026-04-20T10:00:00+00:00",
        b_captured_at="2026-04-26T17:29:01+00:00",
        a_tool_version="0.5.0",
        b_tool_version="0.7.0",
        report_suite_deltas=[],
        components=[
            ComponentDiff(
                component_type="dimensions",
                added=[AddedRemovedItem(id="evar2", name="Plan")],
                removed=[],
                modified=[
                    ModifiedItem(
                        id="evar1",
                        name="User ID",
                        deltas=[FieldDelta(field="type", before="string", after="enum")],
                    ),
                ],
                unchanged_count=10,
            ),
        ],
    )


def test_render_json_returns_string() -> None:
    out = render_json(_stub_report())
    assert isinstance(out, str)


def test_render_json_is_valid_json() -> None:
    out = render_json(_stub_report())
    json.loads(out)  # should not raise


def test_render_json_round_trip_shape() -> None:
    out = render_json(_stub_report())
    data = json.loads(out)
    assert data["a_rsid"] == "demo.prod"
    assert data["components"][0]["component_type"] == "dimensions"
    assert data["components"][0]["added"][0]["id"] == "evar2"
    assert data["components"][0]["modified"][0]["deltas"][0]["field"] == "type"


def test_render_json_keys_sorted() -> None:
    """Output is stable across runs — sort_keys=True."""
    out = render_json(_stub_report())
    # 'a_captured_at' must appear before 'a_rsid' alphabetically
    assert out.find('"a_captured_at"') < out.find('"a_rsid"')
