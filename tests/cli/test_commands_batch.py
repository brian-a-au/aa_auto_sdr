"""cli.commands.batch.run — orchestrates resolve+dedup → run_batch → summary."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

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


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_happy_path_returns_0(mock_client_cls, mock_handle, authed_env, tmp_path, capsys) -> None:
    from aa_auto_sdr.cli.commands import batch as batch_cmd

    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    rc = batch_cmd.run(
        rsids=["demo.prod", "demo.staging"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "[1/2]" in out
    assert "demo.prod" in out
    assert "[2/2]" in out
    assert "demo.staging" in out
    assert "BATCH PROCESSING SUMMARY" in out
    assert "Successful: 2" in out
    assert "Failed: 0" in out


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_partial_success_returns_14(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aa_auto_sdr.cli.commands import batch as batch_cmd
    from aa_auto_sdr.core.exceptions import ApiError
    from aa_auto_sdr.pipeline import single

    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")

    real_run_single = single.run_single

    def fake_run_single(**kwargs):
        if kwargs["rsid"] == "demo.staging":
            raise ApiError("rate limit exceeded")
        return real_run_single(**kwargs)

    monkeypatch.setattr("aa_auto_sdr.pipeline.batch.single.run_single", fake_run_single)

    rc = batch_cmd.run(
        rsids=["demo.prod", "demo.staging", "demo.dev"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == 14  # PARTIAL_SUCCESS
    out = capsys.readouterr().out
    assert "Successful: 2" in out
    assert "Failed: 1" in out
    assert "demo.staging" in out
    assert "rate limit" in out


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_all_fail_returns_last_failure_code(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aa_auto_sdr.cli.commands import batch as batch_cmd
    from aa_auto_sdr.core.exceptions import ApiError, ReportSuiteNotFoundError

    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")

    def fake_run_single(**kwargs):
        if kwargs["rsid"] == "demo.prod":
            raise ApiError("rate")
        raise ReportSuiteNotFoundError("not here")

    monkeypatch.setattr("aa_auto_sdr.pipeline.batch.single.run_single", fake_run_single)

    rc = batch_cmd.run(
        rsids=["demo.prod", "demo.staging"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    # All failed → exit code = last failure's exit_code (ReportSuiteNotFound = 13).
    assert rc == 13


def test_batch_missing_credentials_returns_10(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from aa_auto_sdr.cli.commands import batch as batch_cmd

    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == 10


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_dedups_after_name_resolution(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path,
    capsys,
) -> None:
    """Passing the same RSID twice (or a name + its RSID) must not generate twice."""
    from aa_auto_sdr.cli.commands import batch as batch_cmd

    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    rc = batch_cmd.run(
        rsids=["demo.prod", "demo.prod", "Demo Production"],  # name resolves to demo.prod
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    # After dedup: only one [1/1] line referencing demo.prod
    assert out.count("demo.prod") >= 1
    assert "[1/1]" in out
    assert "[2/" not in out


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_name_lookup_fans_out_within_batch(
    mock_client_cls,
    authed_env,
    tmp_path,
    capsys,
) -> None:
    """A name that matches multiple RSes generates one SDR per match (matches v0.2)."""
    from aa_auto_sdr.cli.commands import batch as batch_cmd

    raw = json.loads(FIXTURE.read_text())
    # Two RSes share the name "Shared Name".
    rs_records = [
        {**raw["report_suite"], "rsid": "rs.a", "name": "Shared Name"},
        {**raw["report_suite"], "rsid": "rs.b", "name": "Shared Name"},
        {**raw["report_suite"], "rsid": "demo.prod", "name": "Demo Production"},
    ]
    handle = MagicMock()
    handle.getReportSuites.return_value = _df(rs_records)
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    rc = batch_cmd.run(
        rsids=["Shared Name"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "[1/2]" in out  # fans out to two RSIDs
    assert "[2/2]" in out
    assert (tmp_path / "rs.a.json").exists()
    assert (tmp_path / "rs.b.json").exists()


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_unknown_rsid_in_resolution_records_failure_and_continues(
    mock_client_cls,
    mock_handle,
    authed_env,
    tmp_path,
    capsys,
) -> None:
    """One bad identifier among many shouldn't abort the whole batch."""
    from aa_auto_sdr.cli.commands import batch as batch_cmd

    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
    rc = batch_cmd.run(
        rsids=["demo.prod", "nonexistent.rsid", "demo.staging"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == 14  # partial success
    out = capsys.readouterr().out
    assert "Successful: 2" in out
    assert "Failed: 1" in out
    assert "nonexistent.rsid" in out


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_snapshot_writes_one_per_success(
    mock_client_cls,
    mock_handle,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json as _json

    from aa_auto_sdr.cli.commands import batch as batch_cmd

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    profile_dir = fake_home / ".aa" / "orgs" / "prod"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.json").write_text(
        _json.dumps(
            {
                "org_id": "O",
                "client_id": "C",
                "secret": "S",
                "scopes": "X",
            }
        )
    )
    mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")

    rc = batch_cmd.run(
        rsids=["demo.prod", "demo.staging"],
        output_dir=tmp_path / "out",
        format_name="json",
        profile="prod",
        snapshot=True,
    )
    assert rc == 0
    snap_root = fake_home / ".aa" / "orgs" / "prod" / "snapshots"
    assert (snap_root / "demo.prod").exists()
    assert (snap_root / "demo.staging").exists()
    assert len(list((snap_root / "demo.prod").glob("*.json"))) == 1


def test_batch_snapshot_without_profile_returns_10(monkeypatch, tmp_path) -> None:
    from aa_auto_sdr.cli.commands import batch as batch_cmd

    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")
    rc = batch_cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        snapshot=True,
    )
    assert rc == 10


# ---------------------------------------------------------------------------
# v1.1 — --auto-snapshot / --auto-prune wiring
# ---------------------------------------------------------------------------


class TestBatchAutoSnapshot:
    @patch("aa_auto_sdr.cli.commands.batch.AaClient")
    def test_auto_snapshot_per_rsid(
        self,
        mock_client_cls,
        mock_handle,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd

        mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
        monkeypatch.setenv("HOME", str(tmp_path))
        prof_dir = tmp_path / ".aa" / "orgs" / "prod"
        prof_dir.mkdir(parents=True)
        (prof_dir / "config.json").write_text(
            json.dumps(
                {
                    "org_id": "O",
                    "client_id": "C",
                    "secret": "S",
                    "scopes": "X",
                }
            )
        )
        rc = batch_cmd.run(
            rsids=["demo.prod", "demo.staging"],
            output_dir=tmp_path / "out",
            format_name="json",
            profile="prod",
            auto_snapshot=True,
        )
        assert rc in (0, 14)  # OK or PARTIAL_SUCCESS
        snap_root = tmp_path / ".aa" / "orgs" / "prod" / "snapshots"
        assert len(list((snap_root / "demo.prod").glob("*.json"))) == 1
        assert len(list((snap_root / "demo.staging").glob("*.json"))) == 1

    def test_auto_snapshot_requires_profile(
        self,
        authed_env,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd

        rc = batch_cmd.run(
            rsids=["demo.prod"],
            output_dir=tmp_path,
            format_name="excel",
            profile=None,
            auto_snapshot=True,
        )
        assert rc == 10
        assert "requires --profile" in capsys.readouterr().out

    @patch("aa_auto_sdr.cli.commands.batch.AaClient")
    def test_auto_prune_applies_policy_per_rsid(
        self,
        mock_client_cls,
        mock_handle,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd

        mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
        monkeypatch.setenv("HOME", str(tmp_path))
        prof_dir = tmp_path / ".aa" / "orgs" / "prod"
        prof_dir.mkdir(parents=True)
        (prof_dir / "config.json").write_text(
            json.dumps(
                {
                    "org_id": "O",
                    "client_id": "C",
                    "secret": "S",
                    "scopes": "X",
                }
            )
        )
        # Pre-seed older snapshots for one RSID
        snap_root = tmp_path / ".aa" / "orgs" / "prod" / "snapshots"
        prod_dir = snap_root / "demo.prod"
        prod_dir.mkdir(parents=True)
        for day in ("20", "21", "22"):
            (prod_dir / f"2026-04-{day}T10-00-00+00-00.json").write_text("{}")
        rc = batch_cmd.run(
            rsids=["demo.prod", "demo.staging"],
            output_dir=tmp_path / "out",
            format_name="json",
            profile="prod",
            auto_snapshot=True,
            auto_prune=True,
            keep_last=1,
        )
        assert rc in (0, 14)
        # demo.prod: 3 pre-seeded + 1 new = 4 → keep-last 1 leaves 1
        assert len(list((snap_root / "demo.prod").glob("*.json"))) == 1
        # demo.staging: 1 new → keep-last 1 leaves 1
        assert len(list((snap_root / "demo.staging").glob("*.json"))) == 1


class TestBatchDryRun:
    @patch("aa_auto_sdr.cli.commands.batch.AaClient")
    def test_dry_run_writes_no_files_in_batch(
        self,
        mock_client_cls,
        mock_handle,
        authed_env,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode

        mock_client_cls.from_credentials.return_value = MagicMock(handle=mock_handle, company_id="testco")
        rc = batch_cmd.run(
            rsids=["demo.prod"],
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            dry_run=True,
        )
        assert rc == ExitCode.OK.value
        # No file written for the RSID
        assert not (tmp_path / "demo.prod.json").exists()
        out = capsys.readouterr().out
        assert "DRY RUN" in out or "would generate" in out


class TestBatchFilteredSnapshotGuard:
    """v1.2 — --metrics-only / --dimensions-only must reject --snapshot / --auto-snapshot
    to prevent persisting misleading filtered envelopes that would falsely diff
    as 'all dimensions removed' against full snapshots."""

    def test_metrics_only_with_snapshot_rejected(
        self,
        authed_env,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode

        rc = batch_cmd.run(
            rsids=["demo.prod"],
            output_dir=tmp_path,
            format_name="excel",
            profile=None,
            metrics_only=True,
            snapshot=True,
        )
        assert rc == ExitCode.USAGE.value
        assert "filtered snapshots" in capsys.readouterr().out

    def test_metrics_only_with_auto_snapshot_rejected(
        self,
        authed_env,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode

        rc = batch_cmd.run(
            rsids=["demo.prod"],
            output_dir=tmp_path,
            format_name="excel",
            profile=None,
            metrics_only=True,
            auto_snapshot=True,
        )
        assert rc == ExitCode.USAGE.value

    def test_dimensions_only_with_snapshot_rejected(
        self,
        authed_env,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd
        from aa_auto_sdr.core.exit_codes import ExitCode

        rc = batch_cmd.run(
            rsids=["demo.prod"],
            output_dir=tmp_path,
            format_name="excel",
            profile=None,
            dimensions_only=True,
            snapshot=True,
        )
        assert rc == ExitCode.USAGE.value
        assert "filtered snapshots" in capsys.readouterr().out
