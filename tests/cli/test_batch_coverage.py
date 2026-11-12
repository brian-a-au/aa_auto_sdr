"""batch command coverage patch: run-summary stdout, format/template/writer guards,
resolve-loop ApiError, dry-run csv/snapshot listing, cache enable+clear, auto-prune
policy branches, open-after, the quality gate, and summary-banner byte edges.
Test-only; no behavior change."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from aa_auto_sdr.cli.commands import batch as batch_cmd
from aa_auto_sdr.core.exit_codes import ExitCode

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


@pytest.fixture
def mock_handle() -> MagicMock:
    raw = json.loads(FIXTURE.read_text())
    rs_records = [
        raw["report_suite"],
        {**raw["report_suite"], "rsid": "demo.staging", "name": "Demo Staging"},
        {**raw["report_suite"], "rsid": "demo.dev", "name": "Demo Dev"},
    ]
    handle = MagicMock()
    handle.getReportSuites.return_value = _df(rs_records)
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    return handle


@pytest.fixture
def authed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


# ---------------------------------------------------------------------------
# Run-summary stdout branch
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_run_summary_json_to_stdout(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--run-summary-json - writes a compact single-line summary to stdout."""
    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")

    def fail_atomic_write(*args, **kwargs) -> None:
        raise AssertionError("stdout must not use atomic file output")

    # Batch writes the summary through generate's shared writer.
    from aa_auto_sdr.cli.commands import generate as generate_cmd

    monkeypatch.setattr(generate_cmd, "atomic_write_text", fail_atomic_write)
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        run_summary_json="-",
    )
    assert rc == ExitCode.OK.value
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["rsids"][0]["rsid"] == "demo.prod"


# The batch summary file before batch shared generate's writer: a frozen copy
# of the old payload, so the shared writer must reproduce it byte for byte.
# The old writer wrote the text with atomic_write_text (platform newlines), so
# the frozen copy goes through the same call: on Windows both files end lines
# with CRLF.
def _legacy_batch_summary_bytes(*, started_at, finished_at, profile, per_rsid, source, path: Path) -> bytes:
    from aa_auto_sdr.core.run_summary import RunSummary
    from aa_auto_sdr.core.version import __version__

    summary = RunSummary(
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        duration_seconds=(finished_at - started_at).total_seconds(),
        tool_version=__version__,
        profile=profile,
        rsids=per_rsid,
        timings=[],
        sampled=source.sampled if source is not None else False,
        sample_size=source.sample_size if source is not None else None,
        sample_seed=source.sample_seed if source is not None else None,
        sample_strategy=source.sample_strategy if source is not None else None,
        total_available=source.total_available if source is not None else 0,
    )
    from aa_auto_sdr.core.atomic_io import atomic_write_text

    atomic_write_text(path, json.dumps(summary.to_dict(), sort_keys=True, indent=2) + "\n")
    return path.read_bytes()


def _summary_sources():
    from aa_auto_sdr.pipeline.batch import SampleOutcome
    from aa_auto_sdr.pipeline.models import BatchResult

    return [
        ("no-sample", {}, None),
        (
            "batch-result-sampled",
            {
                "batch_result": BatchResult(
                    sampled=True, sample_size=2, sample_seed=7, sample_strategy="stratified", total_available=5
                )
            },
            "batch_result",
        ),
        ("batch-result-unsampled", {"batch_result": BatchResult(total_available=3)}, "batch_result"),
        (
            "dry-run-sample",
            {
                "sample": SampleOutcome(
                    rsids=["a", "b"],
                    total_available=4,
                    sampled=True,
                    sample_size=2,
                    sample_seed=1,
                    sample_strategy="random",
                )
            },
            "sample",
        ),
    ]


@pytest.mark.parametrize("case", _summary_sources(), ids=lambda c: c[0])
def test_batch_run_summary_file_bytes_unchanged(case, tmp_path: Path, capsys) -> None:
    from datetime import UTC, datetime

    from aa_auto_sdr.core.run_summary import PerRsidResult

    _name, kwargs, source_key = case
    started = datetime(2026, 11, 11, 9, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 11, 11, 9, 0, 3, 250000, tzinfo=UTC)
    per_rsid = [
        PerRsidResult(rsid="demo.prod", name="Demo", succeeded=True, formats=["json"], output_paths=["/x/a.json"]),
        PerRsidResult(rsid="demo.dev", name=None, succeeded=False, error="ApiError: boom"),
    ]
    target = tmp_path / "summary.json"
    ok = batch_cmd._emit_run_summary(
        run_summary_json=str(target),
        started_at=started,
        finished_at=finished,
        profile="prod",
        per_rsid=per_rsid,
        show_timings=False,
        **kwargs,
    )
    assert ok is True
    expected = _legacy_batch_summary_bytes(
        started_at=started,
        finished_at=finished,
        profile="prod",
        per_rsid=per_rsid,
        source=kwargs[source_key] if source_key else None,
        path=tmp_path / "legacy.json",
    )
    assert target.read_bytes() == expected
    captured = capsys.readouterr()
    assert captured.out == f"wrote run summary: {target}\n"
    assert captured.err == ""


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), reason="needs POSIX perms")
@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_run_summary_write_failure_names_the_users_path(
    mock_client_cls, mock_handle, authed_env, tmp_path: Path, capsys
) -> None:
    """Batch reports the path the user gave, not the hidden staging file, the
    same way generate does."""
    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    ro = tmp_path / "ro"
    ro.mkdir()
    target = str(ro / "summary.json")
    os.chmod(ro, 0o500)
    try:
        rc = batch_cmd.run(
            rsids=["demo.prod"],
            output_dir=tmp_path / "out",
            format_name="json",
            profile=None,
            run_summary_json=target,
        )
    finally:
        os.chmod(ro, 0o700)
    assert rc == ExitCode.OUTPUT.value
    err_lines = capsys.readouterr().err.strip().splitlines()
    assert f"error: could not write run summary {target}: Permission denied" in err_lines
    assert ".summary." not in "\n".join(err_lines)


# ---------------------------------------------------------------------------
# Format / template / writer pre-flight guards
# ---------------------------------------------------------------------------


def test_batch_metrics_and_dimensions_only_mutex(authed_env, tmp_path: Path, capsys) -> None:
    """--metrics-only + --dimensions-only is rejected → USAGE (2)."""
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        metrics_only=True,
        dimensions_only=True,
    )
    assert rc == ExitCode.USAGE.value
    assert "mutually exclusive" in capsys.readouterr().err


def test_batch_unknown_format_returns_output(authed_env, tmp_path: Path, capsys) -> None:
    """resolve_formats raises KeyError for an unknown alias → OUTPUT (15),
    matching the single-generate and list/inspect/diff behavior."""
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="bogus",
        profile=None,
    )
    assert rc == ExitCode.OUTPUT.value
    assert "error:" in capsys.readouterr().err


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_template_path_swaps_excel_for_template(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--template swaps 'excel' → 'excel-template' before run_batch sees the list."""
    from aa_auto_sdr.pipeline import batch as batch_runner
    from aa_auto_sdr.pipeline.models import BatchResult, RunResult

    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")

    captured: dict = {}

    def fake_run_batch(**kwargs):
        captured["formats"] = kwargs["formats"]
        captured["template_path"] = kwargs["template_path"]
        return BatchResult(
            successes=[RunResult(rsid="demo.prod", success=True, outputs=[], report_suite_name="Demo Production")],
            failures=[],
            total_duration_seconds=0.1,
            total_output_bytes=0,
        )

    monkeypatch.setattr(batch_runner, "run_batch", fake_run_batch)
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="excel",
        profile=None,
        template_path=tmp_path / "tpl.xlsx",
    )
    assert rc == ExitCode.OK.value
    assert captured["formats"] == ["excel-template"]
    assert captured["template_path"] == tmp_path / "tpl.xlsx"


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_writer_unavailable_returns_output(
    mock_client_cls,
    authed_env,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """A resolved format with no registered writer → OUTPUT (15)."""
    from aa_auto_sdr.output import registry

    mock_client_cls.from_credentials.return_value = MagicMock(handle=MagicMock(), company_id="testco")

    def _no_writer(name):
        raise KeyError(name)

    monkeypatch.setattr(registry, "get_writer", _no_writer)
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == ExitCode.OUTPUT.value
    assert "is not available in this build" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Identifier-resolution loop: ApiError
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_resolve_apierror_records_failure(
    mock_client_cls,
    authed_env,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """ApiError while resolving an identifier is recorded; all-failed → API (12)."""
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.core.exceptions import ApiError

    mock_client_cls.from_credentials.return_value = MagicMock(handle=MagicMock(), company_id="testco")

    def boom(*_a, **_k):
        raise ApiError("rate limited")

    monkeypatch.setattr(fetch, "resolve_rsid", boom)
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == ExitCode.API.value
    assert "api error" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Dry-run listing branches (csv per-component + snapshot path)
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_dry_run_csv_with_snapshot_lists_paths(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path: Path,
    capsys,
) -> None:
    """Dry-run csv lists a per-component placeholder; --snapshot lists the snapshot path."""
    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    snap_dir = tmp_path / "snaps"
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="csv",
        profile=None,
        dry_run=True,
        snapshot=True,
        snapshot_dir=snap_dir,
    )
    assert rc == ExitCode.OK.value
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "demo.prod.<component>.csv" in out
    assert str(tmp_path / "demo.prod._manifest.json") in out
    assert "snaps" in out  # snapshot path listed


# ---------------------------------------------------------------------------
# Cache enable + clear
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_enable_and_clear_cache(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path: Path,
) -> None:
    """--enable-cache --clear-cache instantiates and clears a ValidationCache."""
    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        enable_cache=True,
        clear_cache=True,
    )
    assert rc == ExitCode.OK.value


# ---------------------------------------------------------------------------
# Auto-prune policy branches + open-after
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_auto_prune_without_policy_returns_config(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path: Path,
    capsys,
) -> None:
    """--auto-prune without --keep-last/--keep-since → CONFIG (10) before the run."""
    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    snap_dir = tmp_path / "snaps"
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path / "out",
        format_name="json",
        profile=None,
        snapshot=True,
        auto_prune=True,
        snapshot_dir=snap_dir,
    )
    assert rc == ExitCode.CONFIG.value
    assert "--auto-prune requires" in capsys.readouterr().err


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_auto_prune_bad_keep_since_returns_config(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path: Path,
    capsys,
) -> None:
    """An unparseable --keep-since raises ConfigError inside _apply_auto_prune → CONFIG (10)."""
    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    snap_dir = tmp_path / "snaps"
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path / "out",
        format_name="json",
        profile=None,
        snapshot=True,
        auto_prune=True,
        keep_since="garbage",
        snapshot_dir=snap_dir,
    )
    assert rc == ExitCode.CONFIG.value
    assert "error:" in capsys.readouterr().err


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_prune_oserror_logs_warning_and_continues(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A per-RSID OSError during prune logs a warning but does not abort the batch."""
    from aa_auto_sdr.snapshot import store

    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")

    def boom(*_a, **_k):
        raise OSError("disk gone")

    monkeypatch.setattr(store, "prune_snapshots", boom)
    snap_dir = tmp_path / "snaps"
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path / "out",
        format_name="json",
        profile=None,
        snapshot=True,
        auto_prune=True,
        keep_last=1,
        snapshot_dir=snap_dir,
    )
    assert rc == ExitCode.OK.value


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_open_after_invokes_os_open(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--open-after opens the output directory via os_open after a successful batch."""
    from aa_auto_sdr.core import _open

    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    calls: list[Path] = []

    def _record(path: Path) -> None:
        calls.append(path)

    monkeypatch.setattr(_open, "os_open", _record)
    out_dir = tmp_path / "out"
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=out_dir,
        format_name="json",
        profile=None,
        open_after=True,
    )
    assert rc == ExitCode.OK.value
    assert calls == [out_dir]


# ---------------------------------------------------------------------------
# Quality gate + summary-banner byte edges
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_quality_fail_returns_quality_and_handles_banner_edges(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """A clean batch with a 'fail' quality verdict returns QUALITY (17). The crafted
    result also exercises the banner's MB formatting and the missing-output getsize
    OSError-continue branch."""
    from aa_auto_sdr.pipeline import batch as batch_runner
    from aa_auto_sdr.pipeline.models import BatchResult, RunResult

    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    missing = tmp_path / "ghost" / "demo.prod.json"  # never created → getsize raises OSError

    def fake_run_batch(**_kwargs):
        return BatchResult(
            successes=[
                RunResult(
                    rsid="demo.prod",
                    success=True,
                    outputs=[missing],
                    report_suite_name="Demo Production",
                    duration_seconds=1.0,
                )
            ],
            failures=[],
            total_duration_seconds=1.0,
            total_output_bytes=2 * 1024 * 1024,  # >= 1 MB → MB branch in _humanize_bytes
            quality_verdicts={"demo.prod": "fail"},
        )

    monkeypatch.setattr(batch_runner, "run_batch", fake_run_batch)
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        fail_on_quality="MEDIUM",
    )
    assert rc == ExitCode.QUALITY.value
    out = capsys.readouterr().out
    assert "MB" in out


@pytest.mark.parametrize(
    ("keep_since", "message"),
    [
        (None, "error: --auto-prune requires --keep-last or --keep-since\n"),
        ("0d", "error: --keep-since must be greater than zero (got '0d')\n"),
    ],
)
def test_auto_prune_without_keep_rule_exits_10_before_any_fetch(
    keep_since, message, mock_handle, authed_env, tmp_path: Path, capsys
) -> None:
    """A bad or empty retention policy fails before credentials are resolved,
    with the same message and exit code the after-run check gives, and no
    output is written."""
    out_dir = tmp_path / "out"
    with (
        patch("aa_auto_sdr.cli.commands.batch.credentials.resolve") as mock_resolve,
        patch("aa_auto_sdr.cli.commands.batch.AaClient") as mock_client_cls,
    ):
        mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
        rc = batch_cmd.run(
            rsids=["demo.prod", "demo.staging"],
            output_dir=out_dir,
            format_name="json",
            profile=None,
            snapshot=True,
            auto_prune=True,
            keep_since=keep_since,
            snapshot_dir=tmp_path / "snaps",
        )
    assert rc == ExitCode.CONFIG.value
    assert capsys.readouterr().err == message
    mock_resolve.assert_not_called()
    mock_client_cls.from_credentials.assert_not_called()
    assert not out_dir.exists() or not any(out_dir.iterdir())
    assert not (tmp_path / "snaps").exists()


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_dry_run_auto_prune_without_keep_rule_is_not_checked_early(
    mock_client_cls, mock_handle, authed_env, tmp_path: Path, capsys
) -> None:
    """A dry run never prunes, so the early policy check does not fire: the
    batch lists what it would write and exits 0, as it did before the check."""
    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    out_dir = tmp_path / "out"
    rc = batch_cmd.run(
        rsids=["demo.prod", "demo.staging"],
        output_dir=out_dir,
        format_name="json",
        profile=None,
        dry_run=True,
        snapshot=True,
        auto_prune=True,
        snapshot_dir=tmp_path / "snaps",
    )
    out, err = capsys.readouterr()
    assert rc == ExitCode.OK.value
    assert "DRY RUN" in out
    assert str(out_dir / "demo.prod.json") in out
    assert str(out_dir / "demo.staging.json") in out
    assert "--auto-prune" not in err
    assert not (tmp_path / "snaps").exists()


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_auto_prune_without_keep_rule_or_snapshot_stays_a_no_op(
    mock_client_cls, mock_handle, authed_env, tmp_path: Path, capsys
) -> None:
    """With no snapshot flag, --auto-prune has nothing to prune and stays a
    silent no-op even with no keep rule: exit 0 and every SDR is written."""
    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    out_dir = tmp_path / "out"
    rc = batch_cmd.run(
        rsids=["demo.prod", "demo.staging"],
        output_dir=out_dir,
        format_name="json",
        profile=None,
        auto_prune=True,
        snapshot_dir=tmp_path / "snaps",
    )
    assert rc == ExitCode.OK.value
    assert "--auto-prune" not in capsys.readouterr().err
    assert (out_dir / "demo.prod.json").is_file()
    assert (out_dir / "demo.staging.json").is_file()
    assert not (tmp_path / "snaps").exists()
