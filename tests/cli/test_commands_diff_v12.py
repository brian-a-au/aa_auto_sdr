"""v1.2 diff knobs: --quiet-diff, --diff-labels, --reverse-diff, --warn-threshold,
--changes-only, --show-only, --max-issues, $GITHUB_STEP_SUMMARY append."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_auto_sdr.cli.commands.diff import run
from aa_auto_sdr.core.exit_codes import ExitCode


def _envelope(rsid: str, *, metrics: list[dict] | None = None) -> dict:
    return {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": rsid,
        "captured_at": "2026-04-26T10:00:00+00:00",
        "tool_version": "1.2.0",
        "components": {
            "report_suite": {
                "rsid": rsid,
                "name": rsid,
                "timezone": "UTC",
                "currency": "USD",
                "parent_rsid": None,
            },
            "dimensions": [],
            "metrics": metrics or [],
            "segments": [],
            "calculated_metrics": [],
            "virtual_report_suites": [],
            "classifications": [],
        },
    }


def _write(p: Path, env: dict) -> Path:
    p.write_text(json.dumps(env, sort_keys=True))
    return p


class TestWarnThreshold:
    def test_below_threshold_returns_ok(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        a = _write(tmp_path / "a.json", _envelope("RS1", metrics=[{"id": "m1", "name": "Old"}]))
        b = _write(tmp_path / "b.json", _envelope("RS1", metrics=[{"id": "m1", "name": "New"}]))
        rc = run(
            a=str(a),
            b=str(b),
            format_name="json",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            quiet=False,
            labels=None,
            reverse=False,
            changes_only=False,
            show_only=frozenset(),
            max_issues=None,
            warn_threshold=10,
        )
        assert rc == ExitCode.OK.value

    def test_at_threshold_returns_warn(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # 1 modified change >= threshold of 1 -> exit 3
        a = _write(tmp_path / "a.json", _envelope("RS1", metrics=[{"id": "m1", "name": "Old"}]))
        b = _write(tmp_path / "b.json", _envelope("RS1", metrics=[{"id": "m1", "name": "New"}]))
        rc = run(
            a=str(a),
            b=str(b),
            format_name="json",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            quiet=False,
            labels=None,
            reverse=False,
            changes_only=False,
            show_only=frozenset(),
            max_issues=None,
            warn_threshold=1,
        )
        assert rc == ExitCode.WARN.value

    def test_warn_threshold_uses_full_report_not_filtered(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Even if --show-only filters out a component type, the warn-threshold
        is computed on the FULL report (per spec section 2.4)."""
        a = _write(tmp_path / "a.json", _envelope("RS1", metrics=[{"id": "m1", "name": "Old"}]))
        b = _write(tmp_path / "b.json", _envelope("RS1", metrics=[{"id": "m1", "name": "New"}]))
        rc = run(
            a=str(a),
            b=str(b),
            format_name="json",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            quiet=False,
            labels=None,
            reverse=False,
            changes_only=False,
            show_only=frozenset({"dimensions"}),  # filter OUT metrics
            max_issues=None,
            warn_threshold=1,
        )
        # The metric change is filtered from rendered output, but warn-threshold
        # still sees it -> exit 3
        assert rc == ExitCode.WARN.value


class TestReverseDiff:
    def test_reverse_swaps_a_and_b(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        a = _write(tmp_path / "a.json", _envelope("RS1", metrics=[{"id": "m1", "name": "Old"}]))
        b = _write(tmp_path / "b.json", _envelope("RS1", metrics=[{"id": "m1", "name": "New"}]))
        rc = run(
            a=str(a),
            b=str(b),
            format_name="json",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            quiet=False,
            labels=None,
            reverse=True,
            changes_only=False,
            show_only=frozenset(),
            max_issues=None,
            warn_threshold=None,
        )
        assert rc == ExitCode.OK.value
        out = capsys.readouterr().out
        payload = json.loads(out)
        # With reverse, the metric delta has before="New" after="Old"
        # (canonical comparator order in `components`: dimensions, metrics, segments, ...)
        metrics_diff = next(c for c in payload["components"] if c["component_type"] == "metrics")
        assert any(d["before"] == "New" and d["after"] == "Old" for d in metrics_diff["modified"][0]["deltas"])


class TestShowOnly:
    def test_filters_to_named_types(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        a = _write(tmp_path / "a.json", _envelope("RS1", metrics=[{"id": "m1", "name": "Old"}]))
        b = _write(tmp_path / "b.json", _envelope("RS1", metrics=[{"id": "m1", "name": "New"}]))
        rc = run(
            a=str(a),
            b=str(b),
            format_name="json",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            quiet=False,
            labels=None,
            reverse=False,
            changes_only=False,
            show_only=frozenset({"metrics"}),
            max_issues=None,
            warn_threshold=None,
        )
        assert rc == ExitCode.OK.value
        payload = json.loads(capsys.readouterr().out)
        types = [c["component_type"] for c in payload["components"]]
        assert types == ["metrics"]


class TestMaxIssues:
    def test_caps_added_list(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        a_metrics = [{"id": f"m{i}", "name": f"M{i}"} for i in range(5)]
        b_metrics = a_metrics + [{"id": f"m{i}", "name": f"M{i}"} for i in range(5, 10)]
        a = _write(tmp_path / "a.json", _envelope("RS1", metrics=a_metrics))
        b = _write(tmp_path / "b.json", _envelope("RS1", metrics=b_metrics))
        rc = run(
            a=str(a),
            b=str(b),
            format_name="json",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            quiet=False,
            labels=None,
            reverse=False,
            changes_only=False,
            show_only=frozenset(),
            max_issues=2,
            warn_threshold=None,
        )
        assert rc == ExitCode.OK.value
        payload = json.loads(capsys.readouterr().out)
        metrics_diff = next(c for c in payload["components"] if c["component_type"] == "metrics")
        assert len(metrics_diff["added"]) == 2  # capped from 5


class TestDiffLabels:
    def test_labels_appear_in_json(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        a = _write(tmp_path / "a.json", _envelope("RS1"))
        b = _write(tmp_path / "b.json", _envelope("RS1"))
        rc = run(
            a=str(a),
            b=str(b),
            format_name="json",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            quiet=False,
            labels=("baseline", "candidate"),
            reverse=False,
            changes_only=False,
            show_only=frozenset(),
            max_issues=None,
            warn_threshold=None,
        )
        assert rc == ExitCode.OK.value
        payload = json.loads(capsys.readouterr().out)
        assert payload["a_label"] == "baseline"
        assert payload["b_label"] == "candidate"


class TestQuietDiff:
    def test_quiet_suppresses_unchanged(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        a = _write(tmp_path / "a.json", _envelope("RS1", metrics=[{"id": "m1", "name": "X"}]))
        b = _write(tmp_path / "b.json", _envelope("RS1", metrics=[{"id": "m1", "name": "X"}]))
        rc = run(
            a=str(a),
            b=str(b),
            format_name="console",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            quiet=True,
            labels=None,
            reverse=False,
            changes_only=False,
            show_only=frozenset(),
            max_issues=None,
            warn_threshold=None,
        )
        assert rc == ExitCode.OK.value
        out = capsys.readouterr().out
        assert "unchanged" not in out


class TestStepSummary:
    def test_appends_when_env_set(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        a = _write(tmp_path / "a.json", _envelope("RS1"))
        b = _write(tmp_path / "b.json", _envelope("RS1"))
        summary_path = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
        rc = run(
            a=str(a),
            b=str(b),
            format_name="console",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            quiet=False,
            labels=None,
            reverse=False,
            changes_only=False,
            show_only=frozenset(),
            max_issues=None,
            warn_threshold=None,
        )
        assert rc == ExitCode.OK.value
        # Summary file was created and contains markdown
        assert summary_path.exists()
        content = summary_path.read_text()
        assert "RS1" in content

    def test_no_append_when_env_unset(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        a = _write(tmp_path / "a.json", _envelope("RS1"))
        b = _write(tmp_path / "b.json", _envelope("RS1"))
        rc = run(
            a=str(a),
            b=str(b),
            format_name="json",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            quiet=False,
            labels=None,
            reverse=False,
            changes_only=False,
            show_only=frozenset(),
            max_issues=None,
            warn_threshold=None,
        )
        assert rc == ExitCode.OK.value
        # No new file should appear in tmp_path beyond a/b
        files = sorted(p.name for p in tmp_path.iterdir())
        assert files == ["a.json", "b.json"]
