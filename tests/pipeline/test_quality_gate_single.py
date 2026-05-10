"""v1.12.0 — single-RSID quality gate + report emission integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.pipeline import single
from aa_auto_sdr.sdr.quality import SeverityLevel


def _df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


@pytest.fixture
def stale_client() -> AaClient:
    """Mock AaClient whose dimensions include one MEDIUM-severity stale name."""
    handle = MagicMock()
    handle.getReportSuites.return_value = _df(
        [{"rsid": "rs1", "name": "RS1", "timezone": "UTC", "currency": "USD", "parent_rsid": None}],
    )
    handle.getDimensions.return_value = _df(
        [
            {
                "id": "evar1",
                "name": "page_name",
                "type": "string",
                "category": "Conversion",
                "parent": "",
                "pathable": False,
                "description": None,
            },
            {
                "id": "evar2",
                "name": "v_old_dim",  # stale_keyword:old → MEDIUM
                "type": "string",
                "category": "Conversion",
                "parent": "",
                "pathable": False,
                "description": None,
            },
        ],
    )
    handle.getMetrics.return_value = _df([])
    handle.getSegments.return_value = _df([])
    handle.getCalculatedMetrics.return_value = _df([])
    handle.getVirtualReportSuites.return_value = _df([])
    handle.getClassificationDatasets.return_value = _df([])
    return AaClient(handle=handle, company_id="testco")


def test_run_single_returns_fail_verdict_when_threshold_breached(
    stale_client: AaClient,
    tmp_path: Path,
) -> None:
    result = single.run_single(
        client=stale_client,
        rsid="rs1",
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
        audit_naming=True,
        flag_stale=True,
        fail_on_quality=SeverityLevel.MEDIUM,
    )
    assert result.success is True
    assert result.quality_verdict == "fail"


def test_run_single_returns_pass_verdict_when_no_breach(
    stale_client: AaClient,
    tmp_path: Path,
) -> None:
    result = single.run_single(
        client=stale_client,
        rsid="rs1",
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
        audit_naming=True,
        flag_stale=True,
        fail_on_quality=SeverityLevel.CRITICAL,  # threshold above any actual issue
    )
    assert result.success is True
    assert result.quality_verdict == "pass"


def test_run_single_emits_quality_report_json(
    stale_client: AaClient,
    tmp_path: Path,
) -> None:
    result = single.run_single(
        client=stale_client,
        rsid="rs1",
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
        audit_naming=True,
        flag_stale=True,
        quality_report="json",
    )
    assert result.quality_report_path is not None
    assert result.quality_report_path.exists()
    assert result.quality_report_path.suffix == ".json"
    # The report path is also in result.outputs.
    assert result.quality_report_path in result.outputs


def test_run_single_emits_quality_report_csv(
    stale_client: AaClient,
    tmp_path: Path,
) -> None:
    result = single.run_single(
        client=stale_client,
        rsid="rs1",
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
        audit_naming=True,
        flag_stale=True,
        quality_report="csv",
    )
    assert result.quality_report_path is not None
    text = result.quality_report_path.read_text()
    assert text.startswith("severity,category,type,item_id,item_name,issue\n")


def test_run_single_no_quality_flags_unchanged_behavior(
    stale_client: AaClient,
    tmp_path: Path,
) -> None:
    result = single.run_single(
        client=stale_client,
        rsid="rs1",
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
    )
    assert result.success is True
    assert result.quality_verdict == ""  # no audit ran
    assert result.quality_report_path is None
