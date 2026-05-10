"""v1.12.0 — batch quality-gate aggregation + per-RSID verdicts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.pipeline import batch
from aa_auto_sdr.pipeline.models import BatchResult


def _df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


def _stale_dim(idx: int) -> dict:
    return {
        "id": f"evar{idx}",
        "name": f"v_old_dim{idx}",  # stale_keyword:old → MEDIUM
        "type": "string",
        "category": "Conversion",
        "parent": "",
        "pathable": False,
        "description": None,
    }


def _clean_dim(idx: int) -> dict:
    return {
        "id": f"evar{idx}",
        "name": f"page_name{idx}",
        "type": "string",
        "category": "Conversion",
        "parent": "",
        "pathable": False,
        "description": None,
    }


@pytest.fixture
def stale_client() -> AaClient:
    """Mock that returns one stale dim for every RSID looked up."""
    handle = MagicMock()
    rs_records = [
        {"rsid": "rs1", "name": "RS1", "timezone": "UTC", "currency": "USD", "parent_rsid": None},
        {"rsid": "rs2", "name": "RS2", "timezone": "UTC", "currency": "USD", "parent_rsid": None},
    ]
    handle.getReportSuites.return_value = _df(rs_records)
    handle.getDimensions.return_value = _df([_stale_dim(1), _clean_dim(2)])
    handle.getMetrics.return_value = _df([])
    handle.getSegments.return_value = _df([])
    handle.getCalculatedMetrics.return_value = _df([])
    handle.getVirtualReportSuites.return_value = _df([])
    handle.getClassificationDatasets.return_value = _df([])
    return AaClient(handle=handle, company_id="testco")


def test_batch_quality_verdicts_populated_when_threshold_set(
    stale_client: AaClient,
    tmp_path: Path,
) -> None:
    result = batch.run_batch(
        client=stale_client,
        rsids=["rs1", "rs2"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
        audit_naming=True,
        flag_stale=True,
        fail_on_quality="MEDIUM",
    )
    assert isinstance(result, BatchResult)
    assert set(result.quality_verdicts.keys()) == {"rs1", "rs2"}
    assert all(v == "fail" for v in result.quality_verdicts.values())


def test_batch_quality_verdicts_empty_without_threshold(
    stale_client: AaClient,
    tmp_path: Path,
) -> None:
    result = batch.run_batch(
        client=stale_client,
        rsids=["rs1", "rs2"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
        audit_naming=True,
        flag_stale=True,
    )
    # Audits ran but no threshold → verdicts are "n/a" per RSID.
    # We still record them (any non-empty verdict gets captured).
    assert all(v == "n/a" for v in result.quality_verdicts.values())


def test_batch_no_audits_no_verdicts(
    stale_client: AaClient,
    tmp_path: Path,
) -> None:
    result = batch.run_batch(
        client=stale_client,
        rsids=["rs1", "rs2"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
    )
    # No audits → quality_verdict on each RunResult is empty string → not captured.
    assert result.quality_verdicts == {}


def test_batch_pass_verdict_when_threshold_above_findings(
    stale_client: AaClient,
    tmp_path: Path,
) -> None:
    result = batch.run_batch(
        client=stale_client,
        rsids=["rs1"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
        audit_naming=True,
        flag_stale=True,
        fail_on_quality="CRITICAL",  # above any actual issue
    )
    assert result.quality_verdicts["rs1"] == "pass"


def test_parallel_batch_threads_quality_gate_to_workers(
    stale_client: AaClient,
    tmp_path: Path,
) -> None:
    """Regression: pre-fix, --workers >= 2 silently bypassed --fail-on-quality
    because workers._run_single_for_batch dropped fail_on_quality / quality_report.
    Sequential and parallel paths must produce identical verdicts."""
    seq = batch.run_batch(
        client=stale_client,
        rsids=["rs1", "rs2"],
        formats=["json"],
        output_dir=tmp_path / "seq",
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
        audit_naming=True,
        flag_stale=True,
        fail_on_quality="MEDIUM",
        workers=1,
    )
    par = batch.run_batch(
        client=stale_client,
        rsids=["rs1", "rs2"],
        formats=["json"],
        output_dir=tmp_path / "par",
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
        audit_naming=True,
        flag_stale=True,
        fail_on_quality="MEDIUM",
        workers=2,
    )
    assert seq.quality_verdicts == par.quality_verdicts
    assert all(v == "fail" for v in par.quality_verdicts.values())


def test_parallel_batch_threads_quality_report_to_workers(
    stale_client: AaClient,
    tmp_path: Path,
) -> None:
    """Regression: --quality-report must produce a per-RSID file in parallel mode."""
    out = tmp_path / "out"
    batch.run_batch(
        client=stale_client,
        rsids=["rs1", "rs2"],
        formats=["json"],
        output_dir=out,
        captured_at=datetime(2026, 5, 10, tzinfo=UTC),
        tool_version="1.12.0",
        audit_naming=True,
        flag_stale=True,
        quality_report="json",
        workers=2,
    )
    report_files = list(out.glob("quality_report_*.json"))
    assert {p.name.split("_")[2] for p in report_files} == {"rs1", "rs2"}
