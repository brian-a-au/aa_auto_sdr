"""--compare-with-prev — sugar over `--diff <RSID>@previous <RSID>@latest`."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from aa_auto_sdr.cli.commands import compare_with_prev as cmd
from aa_auto_sdr.cli.commands import diff as diff_cmd
from aa_auto_sdr.core.exit_codes import ExitCode
from tests.cli.test_commands_diff import _write_envelope


class TestSingleRsidDispatch:
    def test_synthesizes_at_previous_at_latest_pair(self) -> None:
        captured: dict = {}

        def _capture(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        with patch.object(diff_cmd, "run", side_effect=_capture):
            cmd.run(
                rsids=["rs1"],
                profile=None,
                format_name=None,
                output=None,
                side_by_side=False,
                summary=False,
                ignore_fields=frozenset(),
                extended_fields=False,
                quiet=False,
                labels=None,
                reverse=False,
                changes_only=False,
                show_only=frozenset(),
                max_issues=None,
                warn_threshold=None,
                color_theme="default",
            )

        assert captured["a"] == "rs1@previous"
        assert captured["b"] == "rs1@latest"


class TestPassThrough:
    def test_format_and_side_by_side_pass_through(self) -> None:
        captured: dict = {}

        def _stub(**kw: object) -> int:
            captured.update(kw)
            return 0

        with patch.object(diff_cmd, "run", side_effect=_stub):
            cmd.run(
                rsids=["rs1"],
                profile="prod",
                format_name="markdown",
                output="-",
                side_by_side=True,
                summary=False,
                ignore_fields=frozenset({"description"}),
                extended_fields=True,
                quiet=False,
                labels=None,
                reverse=False,
                changes_only=False,
                show_only=frozenset(),
                max_issues=None,
                warn_threshold=None,
                color_theme="default",
            )

        assert captured["format_name"] == "markdown"
        assert captured["side_by_side"] is True
        assert captured["extended_fields"] is True
        assert captured["ignore_fields"] == frozenset({"description"})
        assert captured["profile"] == "prod"


class TestNoPositional:
    def test_empty_rsids_returns_usage(self) -> None:
        rc = cmd.run(
            rsids=[],
            profile=None,
            format_name=None,
            output=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
            extended_fields=False,
            quiet=False,
            labels=None,
            reverse=False,
            changes_only=False,
            show_only=frozenset(),
            max_issues=None,
            warn_threshold=None,
            color_theme="default",
        )
        assert rc == ExitCode.USAGE.value


class TestSnapshotDirThreading:
    def test_snapshot_dir_is_forwarded_to_diff_run(self) -> None:
        """compare_with_prev threads snapshot_dir through to diff_cmd.run."""
        from pathlib import Path

        captured: dict = {}

        def _capture(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        explicit = Path("/tmp/explicit_snaps")
        with patch.object(diff_cmd, "run", side_effect=_capture):
            cmd.run(
                rsids=["rs1"],
                profile=None,
                snapshot_dir=explicit,
                format_name=None,
                output=None,
                side_by_side=False,
                summary=False,
                ignore_fields=frozenset(),
                extended_fields=False,
                quiet=False,
                labels=None,
                reverse=False,
                changes_only=False,
                show_only=frozenset(),
                max_issues=None,
                warn_threshold=None,
                color_theme="default",
            )

        assert captured["snapshot_dir"] == explicit


def _history(root: Path, rsid: str) -> None:
    _write_envelope(root / rsid / "2026-04-20.json", rsid, "2026-04-20T10:00:00+00:00")
    _write_envelope(root / rsid / "2026-04-26.json", rsid, dim_name="Customer ID")


@pytest.mark.parametrize("destination", [None, "-", "file"])
def test_multi_json_is_one_complete_document(tmp_path, capsys, destination):
    for rsid in ("rs2", "rs1"):
        _history(tmp_path, rsid)
    output = str(tmp_path / "result.json") if destination == "file" else destination
    rc = cmd.run(rsids=["rs2", "rs1"], profile=None, snapshot_dir=tmp_path, format_name="json", output=output)
    captured = capsys.readouterr()
    payload = json.loads(Path(output).read_text() if destination == "file" else captured.out)
    assert payload["schema"] == "aa-compare-with-prev/v1"
    assert payload["exit_code"] == rc == 0
    assert [r["rsid"] for r in payload["results"]] == ["rs2", "rs1"]
    assert all(r["exit_code"] == 0 and r["report"]["a_rsid"] == r["rsid"] for r in payload["results"])


def test_multi_error_and_unfiltered_warning(tmp_path, capsys):
    _history(tmp_path, "rs1")
    rc = cmd.run(
        rsids=["missing", "rs1"],
        profile=None,
        snapshot_dir=tmp_path,
        format_name="json",
        output="-",
        warn_threshold=1,
        show_only=frozenset({"metrics"}),
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == payload["exit_code"] == 16
    error, warning = payload["results"]
    assert error["exit_code"] == 16
    assert error["error"]["error_type"] == "SnapshotResolveError"
    assert "missing" in error["error"]["error"]
    assert warning["exit_code"] == 3
    assert [c["component_type"] for c in warning["report"]["components"]] == ["metrics"]
    assert json.loads(captured.err)["error"]["code"] == 16


@pytest.mark.parametrize("fmt", ["console", "markdown", "pr-comment"])
def test_multi_text_includes_outcomes_and_errors(tmp_path, capsys, fmt):
    _history(tmp_path, "rs1")
    assert (
        cmd.run(rsids=["rs1", "missing"], profile=None, snapshot_dir=tmp_path, format_name=fmt, output=None, quiet=True)
        == 16
    )
    text = capsys.readouterr().out
    assert "rs1" in text
    assert "exit_code=0" in text
    assert "missing" in text
    assert "exit_code=16" in text
    assert "SnapshotResolveError" in text


def test_single_json_matches_diff(tmp_path, capsys):
    _history(tmp_path, "rs1")
    kwargs = {"profile": None, "snapshot_dir": tmp_path, "format_name": "json", "output": "-", "labels": ("old", "new")}
    assert cmd.run(rsids=["rs1"], **kwargs) == 0
    single = capsys.readouterr().out
    assert diff_cmd.run(a="rs1@previous", b="rs1@latest", **kwargs) == 0
    literal = json.loads(capsys.readouterr().out)
    # Same pair when no filtered history exists; only the explicit time-relative
    # tokens carry the `baseline_chosen_by_time` limitation.
    literal["coverage"]["limitations"].remove("baseline_chosen_by_time")
    assert literal == json.loads(single)
    assert "schema" not in json.loads(single)


def test_multi_output_failure_is_typed_and_preserves_destination(tmp_path, monkeypatch):
    _history(tmp_path, "rs1")
    target = tmp_path / "result.json"
    target.write_text("original")

    def fail_replace(source, destination):
        raise PermissionError("locked")

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_replace)
    assert (
        cmd.run(rsids=["rs1", "missing"], profile=None, snapshot_dir=tmp_path, format_name="json", output=str(target))
        == 15
    )
    assert target.read_text() == "original"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["result.json", "rs1"]


def test_multi_flags_and_full_step_summary(tmp_path, capsys, monkeypatch):
    for rsid in ("rs1", "rs2"):
        _history(tmp_path, rsid)
    summary_path = tmp_path / "step.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    rc = cmd.run(
        rsids=["rs1", "rs2"],
        profile=None,
        snapshot_dir=tmp_path,
        format_name="json",
        output="-",
        reverse=True,
        labels=("before", "after"),
        summary=True,
        changes_only=True,
        max_issues=0,
        warn_threshold=1,
    )
    assert rc == 3
    payload = json.loads(capsys.readouterr().out)
    for result in payload["results"]:
        assert result["exit_code"] == 3
        report = result["report"]
        assert report["a_label"] == "before"
        assert report["b_label"] == "after"
        assert report["a_captured_at"] == "2026-04-26T17:29:01+00:00"
        assert all(not c["modified"] for c in report["components"])
    full = summary_path.read_text()
    assert "rs1" in full
    assert "rs2" in full
    assert "Customer ID" in full
    assert "User ID" in full


def test_all_failed_preserves_duplicate_requests(tmp_path, capsys):
    assert (
        cmd.run(rsids=["missing", "missing"], profile=None, snapshot_dir=tmp_path, format_name="json", output="-") == 16
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert len(payload["results"]) == 2
    assert all(r["rsid"] == "missing" and r["exit_code"] == 16 for r in payload["results"])
    assert len(captured.err.splitlines()) == 2


def test_unexpected_computation_error_remains_visible(tmp_path, monkeypatch):
    def broken_comparison(**kwargs):
        raise RuntimeError("programmer defect")

    monkeypatch.setattr(diff_cmd, "compute_report", broken_comparison)
    with pytest.raises(RuntimeError, match="programmer defect"):
        cmd.run(rsids=["rs1", "rs2"], profile=None, snapshot_dir=tmp_path, format_name="json", output="-")


def test_output_failure_returns_15_through_cli(tmp_path, monkeypatch, capsys):
    from aa_auto_sdr.cli.main import run

    monkeypatch.setattr("aa_auto_sdr.cli.main.setup_logging", lambda _ns: None)

    _history(tmp_path, "rs1")
    target = tmp_path / "out.json"
    target.write_text("original")

    def fail_replace(source, destination):
        raise PermissionError("locked")

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_replace)
    assert (
        run(
            [
                "rs1",
                "missing",
                "--compare-with-prev",
                "--snapshot-dir",
                str(tmp_path),
                "--format",
                "json",
                "--output",
                str(target),
            ]
        )
        == 15
    )
    assert target.read_text() == "original"
    error = json.loads(capsys.readouterr().err.splitlines()[-1])
    assert error["error"]["code"] == 15
    assert error["error"]["type"] == "OutputError"
    assert str(target) in error["error"]["message"]


def test_multi_console_to_file_has_no_ansi(tmp_path, monkeypatch):
    # Multi-RSID renders through diff.render_report directly; a file target
    # must not get escape codes even when stdout is a terminal.
    import sys

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    for rsid in ("rs1", "rs2"):
        _history(tmp_path, rsid)
    out = tmp_path / "multi.txt"
    rc = cmd.run(rsids=["rs1", "rs2"], profile=None, snapshot_dir=tmp_path, format_name="console", output=str(out))
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert "rs2" in text
    assert "\033[" not in text
