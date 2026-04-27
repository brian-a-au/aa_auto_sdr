"""v1.2 generate/batch knobs: --metrics-only, --dimensions-only, etc."""

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


class TestGenerationModifiers:
    @patch("aa_auto_sdr.cli.commands.generate.AaClient")
    def test_metrics_only_skips_dimensions_fetch(
        self,
        mock_client_cls,
        env_creds,
        tmp_path: Path,
    ) -> None:
        raw = json.loads(FIXTURE.read_text())
        handle = _build_handle(raw)
        mock_client_cls.from_credentials.return_value = MagicMock(
            handle=handle,
            company_id="testco",
        )
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            metrics_only=True,
        )
        assert rc == ExitCode.OK.value
        # getMetrics was called; getDimensions was NOT
        assert handle.getMetrics.called
        assert not handle.getDimensions.called

    def test_mutex_of_metrics_only_and_dimensions_only(
        self,
        env_creds,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=tmp_path,
            format_name="excel",
            profile=None,
            metrics_only=True,
            dimensions_only=True,
        )
        assert rc == ExitCode.USAGE.value


class TestDryRun:
    @patch("aa_auto_sdr.cli.commands.generate.AaClient")
    def test_dry_run_writes_no_files(
        self,
        mock_client_cls,
        env_creds,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        raw = json.loads(FIXTURE.read_text())
        mock_client_cls.from_credentials.return_value = MagicMock(
            handle=_build_handle(raw),
            company_id="testco",
        )
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=tmp_path,
            format_name="excel",
            profile=None,
            dry_run=True,
        )
        assert rc == ExitCode.OK.value
        # No output file created
        assert not (tmp_path / "demo.prod.xlsx").exists()
        out = capsys.readouterr().out
        assert "DRY RUN" in out or "would generate" in out

    @patch("aa_auto_sdr.cli.commands.generate.AaClient")
    def test_dry_run_skips_component_fetch(
        self,
        mock_client_cls,
        env_creds,
        tmp_path: Path,
    ) -> None:
        """In dry-run, no API call past the auth round trip."""
        raw = json.loads(FIXTURE.read_text())
        handle = _build_handle(raw)
        mock_client_cls.from_credentials.return_value = MagicMock(
            handle=handle,
            company_id="testco",
        )
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            dry_run=True,
        )
        assert rc == ExitCode.OK.value
        # getReportSuites is called for resolve_rsid (name → RSID)
        # but the heavy component fetches are not.
        assert not handle.getDimensions.called
        assert not handle.getMetrics.called
        assert not handle.getSegments.called
