"""Top-level `coverage` object in diff JSON and --compare-with-prev JSON.

Describes what the comparison compared so a reader can judge its evidence:
`compare_fields`, `ignored_fields`, `component_types`, `settings_fields`,
`settings_policy`, `show_only`, `limitations` (cja_auto_sdr-aligned)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from aa_auto_sdr.cli.commands import compare_with_prev as cwp_cmd
from aa_auto_sdr.cli.commands import diff as diff_cmd
from aa_auto_sdr.output.diff_renderers.json import render_json
from aa_auto_sdr.snapshot.comparator import _EXTENDED_FIELDS_DEFAULT_IGNORE
from aa_auto_sdr.snapshot.diff_coverage import diff_coverage
from aa_auto_sdr.snapshot.models import ComponentDiff, DiffReport
from tests.cli.test_commands_diff import _write_envelope

_TYPES = ["dimensions", "metrics", "segments", "calculated_metrics", "virtual_report_suites", "classifications"]
_KEYS = {
    "compare_fields",
    "ignored_fields",
    "component_types",
    "settings_fields",
    "settings_policy",
    "show_only",
    "limitations",
}


def _report(*components: ComponentDiff) -> DiffReport:
    return DiffReport(
        a_rsid="rs",
        b_rsid="rs",
        a_captured_at="2026-04-20T10:00:00+00:00",
        b_captured_at="2026-04-26T10:00:00+00:00",
        a_tool_version="1",
        b_tool_version="1",
        components=list(components) or [ComponentDiff(component_type=t) for t in _TYPES],
    )


def _pair(tmp_path: Path) -> tuple[str, str]:
    a = _write_envelope(tmp_path / "a.json", "demo.prod", "2026-04-20T10:00:00+00:00")
    b = _write_envelope(tmp_path / "b.json", "demo.prod", dim_name="Customer ID")
    return str(a), str(b)


def _run_json(capsys, a: str, b: str, **kwargs) -> dict:
    assert diff_cmd.run(a=a, b=b, format_name="json", output="-", profile=None, **kwargs) == 0
    return json.loads(capsys.readouterr().out)


def test_default_coverage_shape() -> None:
    cov = diff_coverage(_report())
    assert set(cov) == _KEYS
    assert cov["component_types"] == _TYPES
    assert cov["ignored_fields"] == sorted(_EXTENDED_FIELDS_DEFAULT_IGNORE)
    assert cov["settings_fields"] == ["currency", "name", "parent_rsid", "timezone"]
    assert cov["settings_policy"] == "reported"
    assert cov["show_only"] is None
    assert cov["limitations"] == ["warn_threshold_counts_components_only"]
    # Identity fields are never deltas; default-ignored fields are not compared.
    assert "id" not in cov["compare_fields"]
    assert "rsid" not in cov["compare_fields"]
    assert "description" not in cov["compare_fields"]
    assert {"name", "type", "definition", "precision"} <= set(cov["compare_fields"])
    assert cov["compare_fields"] == sorted(cov["compare_fields"])


def test_extended_fields_drop_default_ignore_set() -> None:
    cov = diff_coverage(_report(), extended_fields=True)
    assert cov["ignored_fields"] == []
    assert {"description", "tags", "owner_id"} <= set(cov["compare_fields"])


def test_ignore_fields_are_listed_and_not_compared() -> None:
    cov = diff_coverage(_report(), ignore_fields=frozenset({"name", "timezone"}), extended_fields=True)
    assert cov["ignored_fields"] == ["name", "timezone"]
    assert "name" not in cov["compare_fields"]
    assert cov["settings_fields"] == ["currency", "parent_rsid"]


def test_show_only_and_limitation() -> None:
    cov = diff_coverage(_report(), show_only=frozenset({"metrics", "dimensions"}))
    assert cov["show_only"] == ["dimensions", "metrics"]
    assert "show_only_does_not_narrow_warn_threshold" in cov["limitations"]


def test_suppressed_families_add_limitations() -> None:
    report = _report(
        ComponentDiff(component_type="dimensions"),
        ComponentDiff(component_type="metrics", suppressed=True, comparability="excluded"),
        ComponentDiff(component_type="segments", suppressed=True, comparability="degraded"),
    )
    cov = diff_coverage(report)
    assert cov["limitations"] == [
        "warn_threshold_counts_components_only",
        "excluded_families_not_compared",
        "suppressed_families_not_compared",
    ]


def test_baseline_by_time_limitation() -> None:
    assert "baseline_chosen_by_time" in diff_coverage(_report(), baseline_by_time=True)["limitations"]


def test_render_json_without_coverage_argument_uses_defaults() -> None:
    data = json.loads(render_json(_report()))
    assert data["coverage"] == diff_coverage(_report())


def test_diff_json_carries_coverage(tmp_path: Path, capsys) -> None:
    a, b = _pair(tmp_path)
    data = _run_json(capsys, a, b)
    assert data["coverage"]["ignored_fields"] == sorted(_EXTENDED_FIELDS_DEFAULT_IGNORE)
    assert data["coverage"]["show_only"] is None
    assert data["coverage"]["limitations"] == ["warn_threshold_counts_components_only"]
    # Existing keys are untouched.
    assert data["components"][0]["component_type"] == "dimensions"


def test_diff_json_coverage_with_flags(tmp_path: Path, capsys) -> None:
    a, b = _pair(tmp_path)
    data = _run_json(
        capsys,
        a,
        b,
        extended_fields=True,
        ignore_fields=frozenset({"category"}),
        show_only=frozenset({"dimensions"}),
    )
    cov = data["coverage"]
    assert cov["ignored_fields"] == ["category"]
    assert "description" in cov["compare_fields"]
    assert cov["show_only"] == ["dimensions"]
    # The full comparison's component types, not just the shown ones.
    assert cov["component_types"] == _TYPES
    assert [c["component_type"] for c in data["components"]] == ["dimensions"]


def test_diff_json_summary_mode_keeps_coverage(tmp_path: Path, capsys) -> None:
    a, b = _pair(tmp_path)
    assert "coverage" in _run_json(capsys, a, b, summary=True)


def test_diff_at_latest_tokens_mark_baseline_by_time(tmp_path: Path, capsys) -> None:
    _write_envelope(tmp_path / "rs1" / "2026-04-20.json", "rs1", "2026-04-20T10:00:00+00:00")
    _write_envelope(tmp_path / "rs1" / "2026-04-26.json", "rs1", dim_name="Customer ID")
    data = _run_json(capsys, "rs1@previous", "rs1@latest", snapshot_dir=tmp_path)
    assert "baseline_chosen_by_time" in data["coverage"]["limitations"]
    data = _run_json(capsys, "rs1@2026-04-20", "rs1@2026-04-26", snapshot_dir=tmp_path)
    assert "baseline_chosen_by_time" not in data["coverage"]["limitations"]


def _history(root: Path, rsid: str) -> None:
    _write_envelope(root / rsid / "2026-04-20.json", rsid, "2026-04-20T10:00:00+00:00")
    _write_envelope(root / rsid / "2026-04-26.json", rsid, dim_name="Customer ID")


def test_compare_with_prev_multi_json_reports_carry_coverage(tmp_path: Path, capsys) -> None:
    for rsid in ("rs1", "rs2"):
        _history(tmp_path, rsid)
    rc = cwp_cmd.run(
        rsids=["rs1", "rs2"],
        profile=None,
        snapshot_dir=tmp_path,
        format_name="json",
        output="-",
        extended_fields=True,
        show_only=frozenset({"metrics"}),
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    for result in payload["results"]:
        cov = result["report"]["coverage"]
        assert cov["ignored_fields"] == []
        assert cov["show_only"] == ["metrics"]
        assert "baseline_chosen_by_time" not in cov["limitations"]  # covering baseline


def test_compare_with_prev_single_json_carries_coverage(tmp_path: Path, capsys) -> None:
    _history(tmp_path, "rs1")
    rc = cwp_cmd.run(rsids=["rs1"], profile=None, snapshot_dir=tmp_path, format_name="json", output="-")
    assert rc == 0
    cov = json.loads(capsys.readouterr().out)["coverage"]
    assert "baseline_chosen_by_time" not in cov["limitations"]  # covering baseline


def test_compare_with_prev_baseline_is_not_chosen_by_time(tmp_path, capsys) -> None:
    """--compare-with-prev picks a covering baseline, so the time-only limitation does not apply."""
    import json as _json

    from aa_auto_sdr.cli.commands import compare_with_prev, diff
    from tests.snapshot.test_comparator_scope import FULL, _env
    from tests.snapshot.test_covering_baseline import T1, T2, T3, _write

    for env in (_env(collected=FULL, captured_at=T1), _env(collected=["metrics"], captured_at=T2)):
        _write(tmp_path, env)
    _write(tmp_path, _env(collected=FULL, captured_at=T3))
    for rsids in (["rs1"], ["rs1", "rs1"]):
        compare_with_prev.run(rsids=rsids, profile=None, snapshot_dir=tmp_path, format_name="json", output="-")
        payload = _json.loads(capsys.readouterr().out)
        reports = [r["report"] for r in payload["results"]] if "results" in payload else [payload]
        for report in reports:
            assert "baseline_chosen_by_time" not in report["coverage"]["limitations"]
    diff.run(a="rs1@previous", b="rs1@latest", format_name="json", output="-", profile=None, snapshot_dir=tmp_path)
    assert "baseline_chosen_by_time" in _json.loads(capsys.readouterr().out)["coverage"]["limitations"]


def _legacy_report(a_tool_version: str) -> DiffReport:
    return dataclasses.replace(_report(), a_tool_version=a_tool_version, b_tool_version="1.24.2")


def test_legacy_capture_fields_are_reported_as_not_compared() -> None:
    """Against a capture older than 1.21.25, --extended-fields skips dimension and
    metric tags, data_group, and extra; coverage must not claim they were compared."""
    cov = diff_coverage(_legacy_report("1.20.0"), extended_fields=True)
    assert "legacy_capture_fields_not_compared" in cov["limitations"]
    # data_group exists only on metrics, so nothing compared it.
    assert "data_group" not in cov["compare_fields"]
    # tags and extra are still compared on segments, calculated metrics, and the rest.
    assert {"tags", "extra"} <= set(cov["compare_fields"])


def test_legacy_capture_limitation_only_when_the_fields_would_be_compared() -> None:
    assert "legacy_capture_fields_not_compared" not in diff_coverage(_legacy_report("1.20.0"))["limitations"]
    current = diff_coverage(_legacy_report("1.21.25"), extended_fields=True)
    assert "legacy_capture_fields_not_compared" not in current["limitations"]
    assert "data_group" in current["compare_fields"]
