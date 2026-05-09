"""Comparator suppression rules — spec §4.7."""

from __future__ import annotations

from typing import Any

from aa_auto_sdr.snapshot.comparator import compare


def _envelope(
    *,
    rsid: str = "rs1",
    captured_at: str = "2026-05-08T10:00:00+00:00",
    tool_version: str = "1.7.1",
    degraded: list[str] | None = None,
    partial: dict[str, str] | None = None,
    vrs_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "aa-sdr-snapshot/v2",
        "rsid": rsid,
        "captured_at": captured_at,
        "tool_version": tool_version,
        "degraded_components": degraded or [],
        "partial_components": partial or {},
        "components": {
            "report_suite": {
                "rsid": rsid,
                "name": rsid,
                "timezone": None,
                "currency": None,
                "parent_rsid": None,
            },
            "dimensions": [],
            "metrics": [],
            "segments": [],
            "calculated_metrics": [],
            "virtual_report_suites": vrs_rows or [],
            "classifications": [],
        },
    }


def _vrs_section(report) -> Any:
    return next(c for c in report.components if c.component_type == "virtual_report_suites")


def test_both_healthy_falls_through_to_normal_diff() -> None:
    a = _envelope(vrs_rows=[{"id": "v1", "name": "V1", "parent_rsid": "rs1"}])
    b = _envelope(vrs_rows=[{"id": "v1", "name": "V1-renamed", "parent_rsid": "rs1"}])
    report = compare(a, b)
    section = _vrs_section(report)
    assert section.suppressed is False
    assert section.suppression_reason is None
    assert len(section.modified) == 1


def test_left_degraded_suppresses_section() -> None:
    a = _envelope(degraded=["virtual_report_suites"])
    b = _envelope(vrs_rows=[{"id": "v1", "name": "V1", "parent_rsid": "rs1"}])
    section = _vrs_section(compare(a, b))
    assert section.suppressed is True
    assert section.suppression_reason == "fetch degraded"


def test_right_degraded_suppresses_section() -> None:
    a = _envelope(vrs_rows=[{"id": "v1", "name": "V1", "parent_rsid": "rs1"}])
    b = _envelope(degraded=["virtual_report_suites"])
    section = _vrs_section(compare(a, b))
    assert section.suppressed is True
    assert section.suppression_reason == "fetch degraded"


def test_partial_left_only_suppresses_with_reason_carrying_level() -> None:
    a = _envelope(partial={"virtual_report_suites": "minimal"})
    b = _envelope(vrs_rows=[{"id": "v1", "name": "V1", "parent_rsid": "rs1"}])
    section = _vrs_section(compare(a, b))
    assert section.suppressed is True
    assert section.suppression_reason == "fetch partial (expansion_level=minimal)"


def test_partial_right_only_suppresses_with_reason_carrying_level() -> None:
    a = _envelope(vrs_rows=[{"id": "v1", "name": "V1", "parent_rsid": "rs1"}])
    b = _envelope(partial={"virtual_report_suites": "minimal"})
    section = _vrs_section(compare(a, b))
    assert section.suppressed is True
    assert section.suppression_reason == "fetch partial (expansion_level=minimal)"


def test_partial_matching_levels_falls_through_to_normal_diff() -> None:
    a = _envelope(
        partial={"virtual_report_suites": "minimal"},
        vrs_rows=[{"id": "v1", "name": "V1", "parent_rsid": "rs1"}],
    )
    b = _envelope(
        partial={"virtual_report_suites": "minimal"},
        vrs_rows=[{"id": "v2", "name": "V2", "parent_rsid": "rs1"}],
    )
    section = _vrs_section(compare(a, b))
    assert section.suppressed is False
    assert section.suppression_reason is None
    assert len(section.added) == 1
    assert len(section.removed) == 1


def test_partial_mismatched_levels_suppresses() -> None:
    a = _envelope(partial={"virtual_report_suites": "reduced"})
    b = _envelope(partial={"virtual_report_suites": "minimal"})
    section = _vrs_section(compare(a, b))
    assert section.suppressed is True
    # `left_level or right_level` picks the left when both are non-None
    assert section.suppression_reason == "fetch partial (expansion_level=reduced)"


def test_classifications_section_suppression_independent_of_vrs() -> None:
    a = _envelope(degraded=["classifications"])
    b = _envelope()
    report = compare(a, b)
    cls = next(c for c in report.components if c.component_type == "classifications")
    vrs = next(c for c in report.components if c.component_type == "virtual_report_suites")
    assert cls.suppressed is True
    assert vrs.suppressed is False
