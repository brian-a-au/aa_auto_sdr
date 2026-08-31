"""Pipeline orchestration for single-RSID generation."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.pipeline import single
from aa_auto_sdr.pipeline.models import RunResult

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


@pytest.fixture
def mock_client() -> AaClient:
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    return AaClient(handle=handle, company_id="testco")


def test_run_single_writes_excel_and_json(mock_client: AaClient, tmp_path: Path) -> None:
    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=["excel", "json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.1.0",
    )
    assert isinstance(result, RunResult)
    assert result.rsid == "demo.prod"
    assert result.success is True
    assert {p.suffix for p in result.outputs} == {".xlsx", ".json"}
    for p in result.outputs:
        assert p.exists()


def test_run_single_default_filename_uses_rsid(mock_client: AaClient, tmp_path: Path) -> None:
    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.1.0",
    )
    [path] = result.outputs
    assert path.name == "demo.prod.json"


def test_run_single_populates_report_suite_name(mock_client: AaClient, tmp_path: Path) -> None:
    """The summary banner needs the friendly name; pipeline/single.py is the
    single source of truth (it's already built the SdrDocument)."""
    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.5.0",
    )
    # The fixture's report_suite has name="Demo Production".
    assert result.report_suite_name == "Demo Production"


def test_run_single_keeps_prior_success_when_later_format_fails(
    mock_client: AaClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    json_target = tmp_path / "demo.prod.json"
    markdown_target = tmp_path / "demo.prod.md"
    json_target.write_bytes(b"old json")
    markdown_target.write_bytes(b"old markdown")
    real_replace = os.replace

    def fail_markdown_replace(source: Path, destination: Path) -> None:
        if destination.suffix == ".md":
            raise PermissionError("markdown destination locked")
        real_replace(source, destination)

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_markdown_replace)

    with pytest.raises(PermissionError, match="markdown destination locked"):
        single.run_single(
            client=mock_client,
            rsid="demo.prod",
            formats=["json", "markdown"],
            output_dir=tmp_path,
            captured_at=datetime(2026, 4, 25, tzinfo=UTC),
            tool_version="1.21.12",
        )

    assert json.loads(json_target.read_text())["tool_version"] == "1.21.12"
    assert markdown_target.read_bytes() == b"old markdown"
    assert [path for path in tmp_path.iterdir() if path.name.startswith(".")] == []
