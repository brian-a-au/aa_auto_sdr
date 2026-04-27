"""cli.commands.diff.run — orchestrates resolve → compare → render → write."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_envelope(
    path: Path,
    rsid: str,
    captured_at: str = "2026-04-26T17:29:01+00:00",
    *,
    dim_id: str = "evar1",
    dim_name: str = "User ID",
    dimensions: list[dict] | None = None,
    metrics: list[dict] | None = None,
    segments: list[dict] | None = None,
    calculated_metrics: list[dict] | None = None,
    virtual_report_suites: list[dict] | None = None,
    classifications: list[dict] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    default_dims = [
        {
            "id": dim_id,
            "name": dim_name,
            "type": "string",
            "category": "Custom",
            "parent": "",
            "pathable": False,
            "description": None,
            "tags": [],
            "extra": {},
        },
    ]

    def _normalize_metric(m: dict) -> dict:
        base = {
            "id": "",
            "name": "",
            "type": "int",
            "category": "Custom",
            "precision": 0,
            "segmentable": True,
            "description": None,
            "tags": [],
            "data_group": None,
            "extra": {},
        }
        base.update(m)
        return base

    raw_metrics = metrics if metrics is not None else []
    norm_metrics = [_normalize_metric(m) for m in raw_metrics]

    path.write_text(
        json.dumps(
            {
                "schema": "aa-sdr-snapshot/v1",
                "rsid": rsid,
                "captured_at": captured_at,
                "tool_version": "0.7.0",
                "components": {
                    "report_suite": {
                        "rsid": rsid,
                        "name": rsid,
                        "timezone": "UTC",
                        "currency": "USD",
                        "parent_rsid": None,
                    },
                    "dimensions": dimensions if dimensions is not None else default_dims,
                    "metrics": norm_metrics,
                    "segments": segments if segments is not None else [],
                    "calculated_metrics": calculated_metrics if calculated_metrics is not None else [],
                    "virtual_report_suites": virtual_report_suites if virtual_report_suites is not None else [],
                    "classifications": classifications if classifications is not None else [],
                },
            },
            sort_keys=True,
        )
    )
    return path


def test_diff_two_paths_returns_0(tmp_path: Path, capsys) -> None:
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_envelope(a, "demo.prod", "2026-04-20T10:00:00+00:00")
    _write_envelope(b, "demo.prod", "2026-04-26T17:29:01+00:00", dim_name="Customer ID")

    rc = diff_cmd.run(
        a=str(a),
        b=str(b),
        format_name=None,
        output=None,
        profile=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "SDR DIFF" in out
    assert "evar1" in out
    assert "User ID" in out
    assert "Customer ID" in out


def test_diff_unknown_path_returns_16(tmp_path: Path, capsys) -> None:
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    rc = diff_cmd.run(
        a=str(tmp_path / "nope.json"),
        b=str(tmp_path / "also-nope.json"),
        format_name=None,
        output=None,
        profile=None,
    )
    assert rc == 16  # SnapshotError
    captured = capsys.readouterr()
    err = captured.out + captured.err
    assert "snapshot" in err.lower() or "not found" in err.lower()


def test_diff_format_json_to_stdout_pipe(tmp_path: Path, capsys) -> None:
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_envelope(a, "demo.prod", "2026-04-20T10:00:00+00:00")
    _write_envelope(b, "demo.prod", "2026-04-26T17:29:01+00:00")

    rc = diff_cmd.run(
        a=str(a),
        b=str(b),
        format_name="json",
        output="-",
        profile=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["a_rsid"] == "demo.prod"


def test_diff_format_markdown_to_file(tmp_path: Path) -> None:
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_envelope(a, "demo.prod", "2026-04-20T10:00:00+00:00")
    _write_envelope(b, "demo.prod", "2026-04-26T17:29:01+00:00")
    out_path = tmp_path / "diff.md"

    rc = diff_cmd.run(
        a=str(a),
        b=str(b),
        format_name="markdown",
        output=str(out_path),
        profile=None,
    )
    assert rc == 0
    text = out_path.read_text()
    assert text.startswith("# SDR Diff")


def test_diff_console_with_output_dash_returns_15(tmp_path: Path) -> None:
    """Console format to stdout pipe is rejected (use json/markdown for piping)."""
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_envelope(a, "demo.prod", "2026-04-20T10:00:00+00:00")
    _write_envelope(b, "demo.prod", "2026-04-26T17:29:01+00:00")

    rc = diff_cmd.run(
        a=str(a),
        b=str(b),
        format_name="console",
        output="-",
        profile=None,
    )
    assert rc == 15


def test_diff_invalid_format_returns_15(tmp_path: Path) -> None:
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_envelope(a, "demo.prod", "2026-04-20T10:00:00+00:00")
    _write_envelope(b, "demo.prod", "2026-04-26T17:29:01+00:00")

    rc = diff_cmd.run(
        a=str(a),
        b=str(b),
        format_name="excel",
        output=None,
        profile=None,
    )
    assert rc == 15


def test_diff_at_token_without_profile_returns_16() -> None:
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    rc = diff_cmd.run(
        a="demo.prod@latest",
        b="demo.prod@previous",
        format_name=None,
        output=None,
        profile=None,
    )
    assert rc == 16


def test_diff_at_tokens_with_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    snap_dir = fake_home / ".aa" / "orgs" / "prod" / "snapshots" / "demo.prod"
    _write_envelope(
        snap_dir / "2026-04-20T10-00-00+00-00.json",
        "demo.prod",
        "2026-04-20T10:00:00+00:00",
    )
    _write_envelope(
        snap_dir / "2026-04-26T17-29-01+00-00.json",
        "demo.prod",
        "2026-04-26T17:29:01+00:00",
    )

    rc = diff_cmd.run(
        a="demo.prod@latest",
        b="demo.prod@previous",
        format_name="json",
        output="-",
        profile="prod",
    )
    assert rc == 0


def test_diff_rsid_mismatch_warning_in_output(tmp_path: Path, capsys) -> None:
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_envelope(a, "demo.prod", "2026-04-20T10:00:00+00:00")
    _write_envelope(b, "demo.staging", "2026-04-26T17:29:01+00:00")

    rc = diff_cmd.run(a=str(a), b=str(b), format_name=None, output=None, profile=None)
    assert rc == 0  # mismatch is a warning, not an error
    out = capsys.readouterr().out
    assert "RSID mismatch" in out


def test_diff_json_pipe_failure_writes_envelope_to_stderr(tmp_path, capsys) -> None:
    """When --format json --output - and resolve fails, stderr gets a JSON envelope."""
    import json as _json

    from aa_auto_sdr.cli.commands import diff as diff_cmd

    rc = diff_cmd.run(
        a=str(tmp_path / "nope.json"),
        b=str(tmp_path / "also-nope.json"),
        format_name="json",
        output="-",
        profile=None,
    )
    assert rc == 16
    captured = capsys.readouterr()
    payload = _json.loads(captured.err.strip())
    assert payload["error"]["code"] == 16
    assert payload["error"]["type"] in ("SnapshotResolveError", "SnapshotSchemaError")


class TestDiffNewKnobs:
    def test_format_pr_comment_works(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from aa_auto_sdr.cli.commands.diff import run
        from aa_auto_sdr.core.exit_codes import ExitCode

        a = _write_envelope(tmp_path / "a.json", "RS1")
        b = _write_envelope(tmp_path / "b.json", "RS1")
        rc = run(
            a=str(a),
            b=str(b),
            format_name="pr-comment",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset(),
        )
        assert rc == ExitCode.OK.value
        out = capsys.readouterr().out
        assert "SDR Diff" in out

    def test_ignore_fields_drops_delta(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from aa_auto_sdr.cli.commands.diff import run
        from aa_auto_sdr.core.exit_codes import ExitCode

        a = _write_envelope(
            tmp_path / "a.json",
            "RS1",
            metrics=[{"id": "m1", "name": "M", "description": "old"}],
        )
        b = _write_envelope(
            tmp_path / "b.json",
            "RS1",
            metrics=[{"id": "m1", "name": "M", "description": "new"}],
        )
        rc = run(
            a=str(a),
            b=str(b),
            format_name="json",
            output=None,
            profile=None,
            side_by_side=False,
            summary=False,
            ignore_fields=frozenset({"description"}),
        )
        assert rc == ExitCode.OK.value
        out = capsys.readouterr().out
        # Either no modified entries, or modified entries with empty deltas
        import json as _json

        payload = _json.loads(out)
        metric_diff = next(c for c in payload["components"] if c["component_type"] == "metrics")
        # description-only change should disappear entirely
        assert metric_diff["modified"] == []

    def test_summary_drops_detail(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from aa_auto_sdr.cli.commands.diff import run
        from aa_auto_sdr.core.exit_codes import ExitCode

        a = _write_envelope(
            tmp_path / "a.json",
            "RS1",
            metrics=[{"id": "m1", "name": "Old"}],
        )
        b = _write_envelope(
            tmp_path / "b.json",
            "RS1",
            metrics=[{"id": "m1", "name": "New"}],
        )
        rc = run(
            a=str(a),
            b=str(b),
            format_name="markdown",
            output=None,
            profile=None,
            side_by_side=False,
            summary=True,
            ignore_fields=frozenset(),
        )
        assert rc == ExitCode.OK.value
        out = capsys.readouterr().out
        assert "metrics" in out.lower()
