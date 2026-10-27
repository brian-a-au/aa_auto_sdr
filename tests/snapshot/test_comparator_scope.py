"""Scope-aware comparison: a filtered capture never yields false removals or additions.

Rules per family F (source = a, target = b):
- collected on both sides → normal diff; degraded / partial suppression still applies.
- excluded (known) on either side → suppressed, "not collected in source|target".
- unknown scope (legacy, no `collected_components`) with an empty F while the
  other side has rows → suppressed, "capture scope unknown (legacy snapshot)".
- unknown scope with rows → treated as collected.
- unknown and empty on both sides → comparable, zero changes.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from aa_auto_sdr.output.diff_renderers.json import render_json
from aa_auto_sdr.sdr.document import COMPONENT_FAMILIES
from aa_auto_sdr.snapshot.comparator import compare

_ROWS: dict[str, list[dict[str, Any]]] = {
    "dimensions": [{"id": "variables/evar1", "name": "eVar 1"}],
    "metrics": [{"id": "metrics/pageviews", "name": "Page Views"}],
    "segments": [{"id": "s_1", "name": "Segment"}],
    "calculated_metrics": [{"id": "cm_1", "name": "CM"}],
    "virtual_report_suites": [{"id": "vrs_1", "name": "VRS"}],
    "classifications": [{"id": "c_1", "name": "Classification"}],
}


def _env(
    *,
    collected: list[str] | None,
    populated: tuple[str, ...] | None = None,
    captured_at: str = "2026-10-27T00:00:00+00:00",
    degraded: list[str] | None = None,
    partial: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Envelope with rows for `populated` (default: every collected family)."""
    if populated is None:
        populated = tuple(collected) if collected is not None else COMPONENT_FAMILIES
    env: dict[str, Any] = {
        "schema": "aa-sdr-snapshot/v4",
        "rsid": "rs1",
        "captured_at": captured_at,
        "tool_version": "1.22.0",
        "degraded_components": degraded or [],
        "partial_components": partial or {},
        "quality": None,
        "components": {
            "report_suite": {"rsid": "rs1", "name": "RS"},
            **{f: (list(_ROWS[f]) if f in populated else []) for f in COMPONENT_FAMILIES},
        },
    }
    if collected is not None:
        env["collected_components"] = sorted(collected)
        if sorted(collected) != list(COMPONENT_FAMILIES):
            env["schema"] = "aa-sdr-snapshot/v5"
    return env


FULL = list(COMPONENT_FAMILIES)


def _section(report, family: str):
    return next(c for c in report.components if c.component_type == family)


def _lifecycle_total(report) -> int:
    return sum(len(c.added) + len(c.removed) + len(c.modified) for c in report.components if not c.suppressed)


def test_full_to_filtered_gives_no_lifecycle_changes() -> None:
    report = compare(_env(collected=FULL), _env(collected=["metrics"]))
    assert _lifecycle_total(report) == 0
    for family in COMPONENT_FAMILIES:
        section = _section(report, family)
        if family == "metrics":
            assert not section.suppressed
            assert section.comparability == "comparable"
        else:
            assert section.suppressed
            assert section.suppression_reason == "not collected in target"
            assert section.comparability == "excluded"


def test_filtered_to_full_gives_no_lifecycle_changes() -> None:
    report = compare(_env(collected=["dimensions"]), _env(collected=FULL))
    assert _lifecycle_total(report) == 0
    segments = _section(report, "segments")
    assert segments.suppressed
    assert segments.suppression_reason == "not collected in source"
    assert segments.comparability == "excluded"


def test_populated_to_healthy_empty_still_reports_removals() -> None:
    report = compare(_env(collected=FULL), _env(collected=FULL, populated=("metrics",)))
    segments = _section(report, "segments")
    assert not segments.suppressed
    assert [item.id for item in segments.removed] == ["s_1"]
    assert segments.comparability == "comparable"


def test_repeated_filtered_pair_diffs_normally() -> None:
    a = _env(collected=["metrics"])
    b = _env(collected=["metrics"], populated=())
    report = compare(a, b)
    metrics = _section(report, "metrics")
    assert not metrics.suppressed
    assert [item.id for item in metrics.removed] == ["metrics/pageviews"]
    assert _section(report, "dimensions").comparability == "excluded"
    assert _section(report, "dimensions").suppression_reason == "not collected in either snapshot"


@pytest.mark.parametrize("legacy_side", ["source", "target"])
def test_legacy_empty_family_against_rows_is_scope_unknown(legacy_side: str) -> None:
    legacy = _env(collected=None, populated=("metrics",))
    current = _env(collected=FULL)
    a, b = (legacy, current) if legacy_side == "source" else (current, legacy)
    report = compare(a, b)
    segments = _section(report, "segments")
    assert segments.suppressed
    assert segments.suppression_reason == "capture scope unknown (legacy snapshot)"
    assert segments.comparability == "unknown"
    assert _lifecycle_total(report) == 0


def test_legacy_rows_are_treated_as_collected() -> None:
    legacy = _env(collected=None)
    current = _env(collected=FULL, populated=("metrics",))
    segments = _section(compare(legacy, current), "segments")
    assert not segments.suppressed
    assert [item.id for item in segments.removed] == ["s_1"]


def test_legacy_empty_against_empty_is_comparable() -> None:
    legacy = _env(collected=None, populated=())
    current = _env(collected=FULL, populated=())
    segments = _section(compare(legacy, current), "segments")
    assert not segments.suppressed
    assert segments.comparability == "comparable"


def test_excluded_against_legacy_rows_is_excluded() -> None:
    report = compare(_env(collected=None), _env(collected=["metrics"]))
    segments = _section(report, "segments")
    assert segments.suppression_reason == "not collected in target"
    assert segments.comparability == "excluded"


def test_degraded_and_partial_get_their_own_comparability() -> None:
    a = _env(collected=FULL, degraded=["classifications"], partial={"virtual_report_suites": "minimal"})
    report = compare(a, _env(collected=FULL))
    assert _section(report, "classifications").comparability == "degraded"
    assert _section(report, "classifications").suppression_reason == "fetch degraded"
    assert _section(report, "virtual_report_suites").comparability == "partial"


def test_excluded_wins_over_degraded_on_the_other_side() -> None:
    a = _env(collected=["metrics"])
    b = _env(collected=FULL, degraded=["classifications"])
    classifications = _section(compare(a, b), "classifications")
    assert classifications.comparability == "excluded"
    assert classifications.suppression_reason == "not collected in source"


def test_json_diff_carries_comparability() -> None:
    payload = json.loads(render_json(compare(_env(collected=FULL), _env(collected=["metrics"]))))
    by_type = {c["component_type"]: c for c in payload["components"]}
    assert by_type["metrics"]["comparability"] == "comparable"
    assert by_type["segments"]["comparability"] == "excluded"


def test_known_fetch_problem_wins_over_legacy_unknown() -> None:
    """A degraded or partial marker explains an empty legacy family better than "unknown"."""
    legacy = _env(collected=None, populated=("metrics",), degraded=["segments"], partial={"classifications": "min"})
    report = compare(legacy, _env(collected=FULL))
    assert _section(report, "segments").comparability == "degraded"
    assert _section(report, "classifications").comparability == "partial"
    assert _section(report, "dimensions").comparability == "unknown"


def test_excluded_and_unknown_sections_carry_no_raw_rows() -> None:
    """The uncollected side has no data, so its "removals" are not evidence; JSON must not list them."""
    for a, b, family in (
        (_env(collected=FULL), _env(collected=["metrics"]), "segments"),
        (_env(collected=None, populated=("metrics",)), _env(collected=FULL), "segments"),
    ):
        section = _section(compare(a, b), family)
        assert section.suppressed
        assert (section.added, section.removed, section.modified, section.unchanged_count) == ([], [], [], 0)
    payload = json.loads(render_json(compare(_env(collected=FULL), _env(collected=["metrics"]))))
    segments = next(c for c in payload["components"] if c["component_type"] == "segments")
    assert segments["removed"] == []
