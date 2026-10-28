"""Snapshots written before upstream capture fixes must not diff as changes.

Two artifacts of older captures, both observed against a live org:

- Before 1.21.5, ragged DataFrame cells were written as the literal string
  "nan" (parent_rsid, description, category, ...). The reader treats those as
  missing, in memory only.
- Before 1.21.25, dimension and metric `tags`, `data_group`, and `extra` were
  not collected, so `--extended-fields` must not report them as changed
  against a newer capture.
"""

from __future__ import annotations

import copy
import logging

import pytest

from aa_auto_sdr.snapshot.comparator import compare
from aa_auto_sdr.snapshot.schema import captured_before, validate_envelope


def _envelope(tool_version: str, *, report_suite: dict | None = None, **families: list[dict]) -> dict:
    components = {
        "report_suite": report_suite or {"rsid": "rs1", "name": "Demo", "parent_rsid": None},
        "dimensions": [],
        "metrics": [],
        "segments": [],
        "calculated_metrics": [],
        "virtual_report_suites": [],
        "classifications": [],
    }
    components.update(families)
    return {
        "schema": "aa-sdr-snapshot/v4",
        "rsid": "rs1",
        "captured_at": "2026-06-19T23:03:56+00:00",
        "tool_version": tool_version,
        "degraded_components": [],
        "partial_components": {},
        "quality": None,
        "components": components,
    }


def _dim(**fields) -> dict:
    row = {"id": "variables/page", "name": "Page", "type": "string", "category": None, "description": None}
    row.update(fields)
    return row


def _metric(**fields) -> dict:
    row = {"id": "metrics/visits", "name": "Visits", "type": "int", "category": "Traffic", "description": None}
    row.update(fields)
    return row


class TestCapturedBefore:
    @pytest.mark.parametrize(
        ("version", "expected"),
        [("1.18.0", True), ("1.21.4", True), ("1.21.5", False), ("1.24.1", False), ("2.0.0", False)],
    )
    def test_compares_numerically(self, version: str, expected: bool) -> None:
        assert captured_before({"tool_version": version}, (1, 21, 5)) is expected

    @pytest.mark.parametrize("version", ["", "dev", None, 7, "1.x"])
    def test_unparseable_version_is_treated_as_current(self, version: object) -> None:
        assert captured_before({"tool_version": version}, (1, 21, 5)) is False

    def test_suffixes_after_the_numeric_core_are_ignored(self) -> None:
        assert captured_before({"tool_version": "1.21.4.post1"}, (1, 21, 5)) is True
        assert captured_before({"tool_version": "1.21"}, (1, 21, 5)) is True


class TestLegacyNanScrub:
    def test_pre_fix_literal_nan_strings_load_as_missing(self) -> None:
        env = _envelope(
            "1.18.0",
            report_suite={"rsid": "rs1", "name": "Demo", "parent_rsid": "nan", "timezone": "US/Pacific"},
            dimensions=[_dim(category="nan", description="nan")],
        )
        validate_envelope(env)
        assert env["components"]["report_suite"]["parent_rsid"] is None
        assert env["components"]["report_suite"]["timezone"] == "US/Pacific"
        assert env["components"]["dimensions"][0]["category"] is None
        assert env["components"]["dimensions"][0]["description"] is None

    def test_nan_strings_in_current_captures_are_real_values(self) -> None:
        env = _envelope("1.21.5", dimensions=[_dim(description="nan")])
        validate_envelope(env)
        assert env["components"]["dimensions"][0]["description"] == "nan"

    def test_nested_values_are_left_alone(self) -> None:
        env = _envelope("1.18.0", segments=[{"id": "s1", "name": "S", "definition": {"str": "nan"}}])
        validate_envelope(env)
        assert env["components"]["segments"][0]["definition"] == {"str": "nan"}

    def test_report_suite_header_diff_is_clean_across_the_fix(self) -> None:
        old = _envelope("1.18.0", report_suite={"rsid": "rs1", "name": "Demo", "parent_rsid": "nan"})
        new = _envelope("1.24.1", report_suite={"rsid": "rs1", "name": "Demo", "parent_rsid": None})
        validate_envelope(old)
        validate_envelope(new)
        assert compare(old, new).report_suite_deltas == []

    def test_extended_description_diff_is_clean_across_the_fix(self) -> None:
        old = _envelope("1.18.0", dimensions=[_dim(description="nan", category="nan")])
        new = _envelope("1.24.1", dimensions=[_dim()])
        validate_envelope(old)
        validate_envelope(new)
        dims = next(c for c in compare(old, new, extended_fields=True).components if c.component_type == "dimensions")
        assert dims.modified == []


class TestLegacyCaptureFields:
    def _pair(self, old_version: str) -> tuple[dict, dict]:
        old = _envelope(old_version, dimensions=[_dim(tags=[], extra={})], metrics=[_metric(extra={})])
        new = _envelope(
            "1.24.1",
            dimensions=[_dim(tags=["core"], extra={"standardComponent": True})],
            metrics=[_metric(data_group="Traffic", extra={"polarity": "positive"})],
        )
        return old, new

    def _modified(self, report, family: str) -> list:
        return next(c for c in report.components if c.component_type == family).modified

    def test_fields_first_collected_in_1_21_25_are_not_compared_against_older_captures(self) -> None:
        old, new = self._pair("1.21.24")
        report = compare(old, new, extended_fields=True)
        assert self._modified(report, "dimensions") == []
        assert self._modified(report, "metrics") == []

    def test_reversed_order_is_also_suppressed(self) -> None:
        old, new = self._pair("1.18.0")
        report = compare(new, old, extended_fields=True)
        assert self._modified(report, "dimensions") == []

    def test_fields_are_compared_when_both_captures_collected_them(self) -> None:
        old, new = self._pair("1.21.25")
        report = compare(old, new, extended_fields=True)
        dim_fields = {d.field for m in self._modified(report, "dimensions") for d in m.deltas}
        metric_fields = {d.field for m in self._modified(report, "metrics") for d in m.deltas}
        assert {"tags", "extra.standardComponent"} <= dim_fields
        assert {"data_group", "extra.polarity"} <= metric_fields

    def test_other_extended_fields_still_compare_against_older_captures(self) -> None:
        old = _envelope("1.18.0", dimensions=[_dim(description="Old")])
        new = _envelope("1.24.1", dimensions=[_dim(description="New")])
        report = compare(old, new, extended_fields=True)
        assert [d.field for m in self._modified(report, "dimensions") for d in m.deltas] == ["description"]

    def test_segment_tags_are_not_affected(self) -> None:
        old = _envelope("1.18.0", segments=[{"id": "s1", "name": "S", "tags": []}])
        new = _envelope("1.24.1", segments=[{"id": "s1", "name": "S", "tags": ["x"]}])
        report = compare(old, new, extended_fields=True)
        assert len(self._modified(report, "segments")) == 1

    def test_warns_once_naming_the_skipped_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        old, new = self._pair("1.18.0")
        with caplog.at_level(logging.WARNING):
            compare(old, new, extended_fields=True)
        records = [r for r in caplog.records if r.getMessage().startswith("diff_legacy_capture_fields")]
        assert len(records) == 1
        assert records[0].not_compared_fields == ["data_group", "extra", "tags"]

    def test_no_warning_without_extended_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        old, new = self._pair("1.18.0")
        with caplog.at_level(logging.WARNING):
            compare(old, new)
        assert not [r for r in caplog.records if r.getMessage().startswith("diff_legacy_capture_fields")]

    def test_compare_does_not_mutate_inputs(self) -> None:
        old, new = self._pair("1.18.0")
        before = copy.deepcopy((old, new))
        compare(old, new, extended_fields=True)
        assert (old, new) == before
