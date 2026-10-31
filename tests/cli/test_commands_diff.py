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


def test_diff_format_markdown_to_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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
    capsys.readouterr()

    rc = diff_cmd.run(
        a=str(a),
        b=str(b),
        format_name="markdown",
        output="-",
        profile=None,
    )

    assert rc == 0
    expected = tmp_path / "expected.md"
    expected.write_text(capsys.readouterr().out)
    assert out_path.read_bytes() == expected.read_bytes()


def test_diff_stdout_bypasses_atomic_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_envelope(a, "demo.prod", "2026-04-20T10:00:00+00:00")
    _write_envelope(b, "demo.prod", "2026-04-26T17:29:01+00:00")

    def fail_atomic_write(*args, **kwargs) -> None:
        raise AssertionError("stdout must not use atomic file output")

    monkeypatch.setattr(diff_cmd, "atomic_write_text", fail_atomic_write)

    rc = diff_cmd.run(
        a=str(a),
        b=str(b),
        format_name="json",
        output="-",
        profile=None,
    )

    assert rc == 0


def test_diff_replace_failure_preserves_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_envelope(a, "demo.prod", "2026-04-20T10:00:00+00:00")
    _write_envelope(b, "demo.prod", "2026-04-26T17:29:01+00:00")
    out_path = tmp_path / "diff.md"
    out_path.write_bytes(b"original diff")

    def fail_replace(source: Path, destination: Path) -> None:
        raise PermissionError("destination locked")

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_replace)

    rc = diff_cmd.run(
        a=str(a),
        b=str(b),
        format_name="markdown",
        output=str(out_path),
        profile=None,
    )

    # A failed write is a clean OUTPUT exit, not a traceback; the atomic
    # writer still leaves the original file and no staging file behind.
    assert rc == 15
    assert out_path.read_bytes() == b"original diff"
    assert [path for path in tmp_path.iterdir() if path.name.startswith(".")] == []


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


class TestDiffHonorsSnapshotDir:
    def test_diff_resolves_at_tokens_from_explicit_dir(
        self,
        tmp_path: Path,
    ) -> None:
        """--diff with --snapshot-dir resolves <rsid>@latest/<rsid>@previous
        from the explicit dir, not from a profile path."""
        snap_dir = tmp_path / "snaps"
        _write_envelope(
            snap_dir / "RS1" / "2026-05-12T10-00-00+00-00.json",
            rsid="RS1",
            captured_at="2026-05-12T10:00:00+00:00",
        )
        _write_envelope(
            snap_dir / "RS1" / "2026-05-13T10-00-00+00-00.json",
            rsid="RS1",
            captured_at="2026-05-13T10:00:00+00:00",
        )
        from aa_auto_sdr.cli.commands import diff as diff_mod

        rc = diff_mod.run(
            a="RS1@previous",
            b="RS1@latest",
            format_name="json",
            output="-",
            profile=None,
            snapshot_dir=snap_dir,
        )
        assert rc == 0

    def test_explicit_dir_wins_over_profile(
        self,
        tmp_path: Path,
    ) -> None:
        """When both --profile and --snapshot-dir are set on --diff,
        snapshot_dir wins (success criterion §6.5). Pass a deliberately
        nonexistent profile name; the resolution must still succeed."""
        snap_dir = tmp_path / "snaps"
        _write_envelope(
            snap_dir / "RS1" / "2026-05-12T10-00-00+00-00.json",
            rsid="RS1",
            captured_at="2026-05-12T10:00:00+00:00",
        )
        _write_envelope(
            snap_dir / "RS1" / "2026-05-13T10-00-00+00-00.json",
            rsid="RS1",
            captured_at="2026-05-13T10:00:00+00:00",
        )
        from aa_auto_sdr.cli.commands import diff as diff_mod

        rc = diff_mod.run(
            a="RS1@previous",
            b="RS1@latest",
            format_name="json",
            output="-",
            profile="nonexistent_garbage_profile",
            snapshot_dir=snap_dir,
        )
        assert rc == 0


def _non_ascii_pair(tmp_path: Path) -> tuple[Path, Path]:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write_envelope(a, "demo.prod", "2026-04-20T10:00:00+00:00", dim_name="Café")
    _write_envelope(b, "demo.prod", "2026-04-26T17:29:01+00:00", dim_name="Café — 日本")
    return a, b


@pytest.mark.parametrize("fmt", ["pr-comment", "markdown", "console"])
def test_diff_output_file_is_written_as_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fmt: str) -> None:
    # open(encoding=None) follows the locale (cp1252 on Windows), which cannot
    # encode the renderers' glyphs or non-Latin names. Record the encoding the
    # file write asks for and check the bytes on disk.
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    a, b = _non_ascii_pair(tmp_path)
    seen: list[str | None] = []
    real = diff_cmd.atomic_write_text

    def recording(target, content, **kwargs):
        seen.append(kwargs.get("encoding"))
        return real(target, content, **kwargs)

    monkeypatch.setattr(diff_cmd, "atomic_write_text", recording)
    out_path = tmp_path / "diff.out"

    rc = diff_cmd.run(a=str(a), b=str(b), format_name=fmt, output=str(out_path), profile=None)

    assert rc == 0
    assert seen == ["utf-8"]
    assert "日本" in out_path.read_bytes().decode("utf-8")


def test_diff_output_to_directory_returns_output_exit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    a, b = _non_ascii_pair(tmp_path)
    target = tmp_path / "already-a-dir"
    target.mkdir()

    rc = diff_cmd.run(a=str(a), b=str(b), format_name="markdown", output=str(target), profile=None)

    assert rc == 15
    assert capsys.readouterr().err.startswith(f"error: could not write {target}:")


def test_diff_output_parent_blocked_returns_output_exit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # A file where the parent directory should be makes mkdir() raise.
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    a, b = _non_ascii_pair(tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("x")

    rc = diff_cmd.run(a=str(a), b=str(b), format_name="json", output=str(blocker / "diff.json"), profile=None)

    assert rc == 15
    assert "error: could not write" in capsys.readouterr().err
