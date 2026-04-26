"""pipeline.batch.run_batch — sequential continue-on-error orchestration."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core.exceptions import ApiError, ReportSuiteNotFoundError
from aa_auto_sdr.pipeline import batch
from aa_auto_sdr.pipeline.models import BatchResult

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


@pytest.fixture
def mock_client() -> AaClient:
    """A mock client whose handle returns the same fixture for any RSID lookup."""
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


def test_run_batch_returns_batch_result(mock_client: AaClient, tmp_path: Path) -> None:
    """Smoke: at minimum the return type must be BatchResult."""
    result = batch.run_batch(
        client=mock_client,
        rsids=["demo.prod"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.5.0",
    )
    assert isinstance(result, BatchResult)


def test_run_batch_happy_path_all_succeed(mock_client: AaClient, tmp_path: Path) -> None:
    """Three RSIDs all succeed (the fixture handle returns success regardless of rsid)."""
    rsids = ["demo.prod", "demo.staging", "demo.dev"]
    result = batch.run_batch(
        client=mock_client,
        rsids=rsids,
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.5.0",
    )
    assert len(result.successes) == 3
    assert result.failures == []
    assert [r.rsid for r in result.successes] == rsids
    for r in result.successes:
        assert r.success is True
        assert all(p.exists() for p in r.outputs)
    assert result.total_output_bytes > 0
    assert result.total_duration_seconds >= 0.0


def test_run_batch_partial_success_continues_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    mock_client: AaClient,
    tmp_path: Path,
) -> None:
    """If one RSID raises mid-batch, run_batch records the failure and keeps going."""
    real_run_single = batch.single.run_single
    call_count = {"n": 0}

    def fake_run_single(**kwargs):
        call_count["n"] += 1
        if kwargs["rsid"] == "bad.rsid":
            raise ApiError("rate limit exceeded")
        return real_run_single(**kwargs)

    monkeypatch.setattr(batch.single, "run_single", fake_run_single)

    result = batch.run_batch(
        client=mock_client,
        rsids=["demo.prod", "bad.rsid", "demo.staging"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.5.0",
    )

    assert call_count["n"] == 3  # ran all three despite middle failure
    assert [r.rsid for r in result.successes] == ["demo.prod", "demo.staging"]
    assert len(result.failures) == 1
    fail = result.failures[0]
    assert fail.rsid == "bad.rsid"
    assert fail.error_type == "ApiError"
    assert "rate limit" in fail.message
    assert fail.exit_code == 12  # ApiError → 12 per generate.py


def test_run_batch_all_fail(
    monkeypatch: pytest.MonkeyPatch,
    mock_client: AaClient,
    tmp_path: Path,
) -> None:
    def fake_run_single(**kwargs):
        raise ReportSuiteNotFoundError(f"not found: {kwargs['rsid']}")

    monkeypatch.setattr(batch.single, "run_single", fake_run_single)

    result = batch.run_batch(
        client=mock_client,
        rsids=["a", "b"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.5.0",
    )
    assert result.successes == []
    assert [f.rsid for f in result.failures] == ["a", "b"]
    assert all(f.error_type == "ReportSuiteNotFoundError" for f in result.failures)
    assert all(f.exit_code == 13 for f in result.failures)


def test_run_batch_progress_callback_fires_in_order(mock_client: AaClient, tmp_path: Path) -> None:
    seen: list[tuple[int, int, str]] = []
    batch.run_batch(
        client=mock_client,
        rsids=["a.rs", "b.rs", "c.rs"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.5.0",
        progress_callback=lambda i, total, rsid: seen.append((i, total, rsid)),
    )
    assert seen == [(1, 3, "a.rs"), (2, 3, "b.rs"), (3, 3, "c.rs")]


def test_run_batch_failure_callback_fires_with_message(
    monkeypatch: pytest.MonkeyPatch,
    mock_client: AaClient,
    tmp_path: Path,
) -> None:
    def fake_run_single(**kwargs):
        raise ApiError("boom")

    monkeypatch.setattr(batch.single, "run_single", fake_run_single)

    seen: list[tuple[int, int, str, str]] = []
    batch.run_batch(
        client=mock_client,
        rsids=["x.rs"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.5.0",
        failure_callback=lambda i, total, rsid, msg: seen.append((i, total, rsid, msg)),
    )
    assert len(seen) == 1
    i, total, rsid, msg = seen[0]
    assert (i, total, rsid) == (1, 1, "x.rs")
    assert "boom" in msg


def test_run_batch_accumulates_total_output_bytes(mock_client: AaClient, tmp_path: Path) -> None:
    result = batch.run_batch(
        client=mock_client,
        rsids=["a.rs", "b.rs"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.5.0",
    )
    expected = sum(p.stat().st_size for r in result.successes for p in r.outputs)
    assert result.total_output_bytes == expected
    assert result.total_output_bytes > 0


def test_run_batch_preserves_runresult_metadata(mock_client: AaClient, tmp_path: Path) -> None:
    """RunResult.report_suite_name must survive the batch wrap (used by banner)."""
    result = batch.run_batch(
        client=mock_client,
        rsids=["demo.prod"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.5.0",
    )
    assert len(result.successes) == 1
    assert result.successes[0].report_suite_name is not None


def test_run_batch_stamps_per_rsid_duration(mock_client: AaClient, tmp_path: Path) -> None:
    """Per-RSID duration_seconds must be populated for the banner ✓ row."""
    result = batch.run_batch(
        client=mock_client,
        rsids=["demo.prod", "demo.staging"],
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.5.0",
    )
    assert len(result.successes) == 2
    for r in result.successes:
        assert r.duration_seconds >= 0.0
    # Sum of per-RSID durations should be ≤ total wall-clock (with small slack
    # for the inter-call accounting). They won't be exactly equal because the
    # outer timer also covers the brief loop bookkeeping between runs.
    per_rsid_total = sum(r.duration_seconds for r in result.successes)
    assert per_rsid_total <= result.total_duration_seconds + 0.01
