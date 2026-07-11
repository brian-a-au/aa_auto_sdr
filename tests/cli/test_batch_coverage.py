"""batch command coverage patch: run-summary stdout, format/template/writer guards,
resolve-loop ApiError, dry-run csv/snapshot listing, cache enable+clear, auto-prune
policy branches, open-after, the quality gate, and summary-banner byte edges.
Test-only; no behavior change."""

from __future__ import annotations

import json
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
) -> None:
    """--run-summary-json - writes a compact single-line summary to stdout."""
    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
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


def test_batch_unknown_format_returns_generic(authed_env, tmp_path: Path, capsys) -> None:
    """resolve_formats raises KeyError for an unknown alias → GENERIC (1)."""
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="bogus",
        profile=None,
    )
    assert rc == ExitCode.GENERIC.value
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
    """--auto-prune without --keep-last/--keep-since → CONFIG (10) after the run."""
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
