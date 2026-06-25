"""generate command coverage patch: format/template/writer guards, pipe + file
error paths, dry-run csv/snapshot listing, auto-prune policy branches, open-after,
and the quality gate. Test-only; no behavior change."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.commands import generate as cmd
from aa_auto_sdr.core.exit_codes import ExitCode

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


def _build_handle(raw: dict) -> MagicMock:
    import pandas as pd

    handle = MagicMock()
    handle.getReportSuites.return_value = pd.DataFrame([raw["report_suite"]])
    handle.getDimensions.return_value = pd.DataFrame(raw["dimensions"])
    handle.getMetrics.return_value = pd.DataFrame(raw["metrics"])
    handle.getSegments.return_value = pd.DataFrame(raw["segments"])
    handle.getCalculatedMetrics.return_value = pd.DataFrame(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = pd.DataFrame(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = pd.DataFrame(raw["classification_datasets"])
    return handle


# ---------------------------------------------------------------------------
# Format / template / writer pre-flight guards
# ---------------------------------------------------------------------------


def test_generate_unknown_format_returns_generic(env_creds, tmp_path: Path, capsys) -> None:
    """resolve_formats raises KeyError for an unknown alias → GENERIC (1)."""
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="bogus", profile=None)
    assert rc == ExitCode.GENERIC.value
    assert "error:" in capsys.readouterr().out


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_template_path_swaps_excel_for_template(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--template swaps 'excel' → 'excel-template' before the pipeline runs."""
    from aa_auto_sdr.pipeline import single
    from aa_auto_sdr.pipeline.models import RunResult

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")

    captured: dict = {}

    def fake_run_single(**kwargs):
        captured["formats"] = kwargs["formats"]
        captured["template_path"] = kwargs["template_path"]
        return RunResult(rsid="demo.prod", success=True, outputs=[], report_suite_name="Demo Production")

    monkeypatch.setattr(single, "run_single", fake_run_single)
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="excel",
        profile=None,
        template_path=tmp_path / "tpl.xlsx",
    )
    assert rc == ExitCode.OK.value
    assert captured["formats"] == ["excel-template"]
    assert captured["template_path"] == tmp_path / "tpl.xlsx"


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_writer_unavailable_returns_output(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """Vestigial pre-flight: a resolved format with no registered writer → OUTPUT (15)."""
    from aa_auto_sdr.output import registry

    def _no_writer(name):
        raise KeyError(name)

    monkeypatch.setattr(registry, "get_writer", _no_writer)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == ExitCode.OUTPUT.value
    assert "is not available in this build" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# resolve_rsid error path
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_resolve_apierror_returns_api(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """ApiError from resolve_rsid (non-pipe) → API (12) with stdout message."""
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.core.exceptions import ApiError

    mock_client_cls.from_credentials.return_value = MagicMock(handle=MagicMock(), company_id="testco")

    def boom(*_a, **_k):
        raise ApiError("rate limited")

    monkeypatch.setattr(fetch, "resolve_rsid", boom)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == ExitCode.API.value
    assert "api error" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Dry-run listing branches (csv per-component + snapshot path)
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_dry_run_csv_with_snapshot_lists_paths(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys,
) -> None:
    """Dry-run csv lists a per-component placeholder; --snapshot lists the snapshot path."""
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    snap_dir = tmp_path / "snaps"
    rc = cmd.run(
        rsid="demo.prod",
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
# Pipe-path build loop branches
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_build_rsid_not_found_returns_13(
    mock_client_cls,
    env_creds,
    capsys,
) -> None:
    """Pipe path: build_sdr raises ReportSuiteNotFoundError → envelope on stderr, NOT_FOUND (13)."""
    from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    with patch(
        "aa_auto_sdr.cli.commands.generate.build_sdr",
        side_effect=ReportSuiteNotFoundError("vanished mid-build"),
    ):
        rc = cmd.run(rsid="demo.prod", output_dir=Path("-"), format_name="json", profile=None)
    assert rc == ExitCode.NOT_FOUND.value
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err.strip())
    assert payload["error"]["code"] == 13
    assert payload["error"]["type"] == "ReportSuiteNotFoundError"


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_with_snapshot_saves_envelope(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys,
) -> None:
    """Pipe path + --snapshot persists one snapshot envelope alongside the stdout JSON."""
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    snap_dir = tmp_path / "snaps"
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="json",
        profile=None,
        snapshot=True,
        snapshot_dir=snap_dir,
    )
    assert rc == ExitCode.OK.value
    assert (snap_dir / "demo.prod").exists()
    assert len(list((snap_dir / "demo.prod").glob("*.json"))) == 1
    # stdout still carries the SDR JSON value
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["report_suite"]["rsid"] == "demo.prod"


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_auto_prune_without_policy_returns_config(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys,
) -> None:
    """Pipe path + --auto-prune without --keep-last/--keep-since → CONFIG (10) envelope."""
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    snap_dir = tmp_path / "snaps"
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="json",
        profile=None,
        snapshot=True,
        auto_prune=True,
        snapshot_dir=snap_dir,
    )
    assert rc == ExitCode.CONFIG.value


# ---------------------------------------------------------------------------
# File-output run_single error branches
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_file_run_single_rsid_not_found_returns_13(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """ReportSuiteNotFoundError raised inside run_single (file path) → NOT_FOUND (13)."""
    from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError
    from aa_auto_sdr.pipeline import single

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")

    def boom(**_kw):
        raise ReportSuiteNotFoundError("gone mid-run")

    monkeypatch.setattr(single, "run_single", boom)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == ExitCode.NOT_FOUND.value
    assert "error:" in capsys.readouterr().out


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_file_run_single_generic_error_returns_generic(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    """A base AaAutoSdrError from run_single (file path) → GENERIC (1)."""
    from aa_auto_sdr.core.exceptions import AaAutoSdrError
    from aa_auto_sdr.pipeline import single

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")

    def boom(**_kw):
        raise AaAutoSdrError("unexpected internal failure")

    monkeypatch.setattr(single, "run_single", boom)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == ExitCode.GENERIC.value
    assert "error:" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# File-output auto-prune branches + open-after + quality gate
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_file_auto_prune_without_policy_returns_config(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
) -> None:
    """File path + --auto-prune without policy → CONFIG (10) after the SDR writes."""
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    snap_dir = tmp_path / "snaps"
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path / "out",
        format_name="json",
        profile=None,
        snapshot=True,
        auto_prune=True,
        snapshot_dir=snap_dir,
    )
    assert rc == ExitCode.CONFIG.value


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_auto_prune_bad_keep_since_returns_config(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys,
) -> None:
    """An unparseable --keep-since raises ConfigError inside _apply_auto_prune → CONFIG (10)."""
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    snap_dir = tmp_path / "snaps"
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path / "out",
        format_name="json",
        profile=None,
        snapshot=True,
        auto_prune=True,
        keep_since="garbage",
        snapshot_dir=snap_dir,
    )
    assert rc == ExitCode.CONFIG.value
    assert "error:" in capsys.readouterr().out


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_open_after_invokes_os_open(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--open-after on a successful file run opens the first output via os_open."""
    from aa_auto_sdr.core import _open

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")

    calls: list[Path] = []

    def _record(path: Path) -> None:
        calls.append(path)

    monkeypatch.setattr(_open, "os_open", _record)
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        open_after=True,
    )
    assert rc == ExitCode.OK.value
    assert len(calls) == 1
    assert calls[0].name == "demo.prod.json"


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_quality_fail_returns_quality(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """File path: a successful RSID whose quality verdict is 'fail' under
    --fail-on-quality returns QUALITY (17), a soft signal after a clean write."""
    from aa_auto_sdr.pipeline import single
    from aa_auto_sdr.pipeline.models import RunResult

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")

    def fake_run_single(**_kw):
        return RunResult(
            rsid="demo.prod",
            success=True,
            outputs=[],
            report_suite_name="Demo Production",
            quality_verdict="fail",
        )

    monkeypatch.setattr(single, "run_single", fake_run_single)
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        fail_on_quality="MEDIUM",
    )
    assert rc == ExitCode.QUALITY.value
