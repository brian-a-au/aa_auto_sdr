"""Integration tests: fetchers consume client.retry_policy and retry on
SDK-shape transient failures.

Per spike (docs/superpowers/spikes/2026-05-08-aanalytics2-resilience-spike.md):
aanalytics2 0.5.1 sets urllib3.Retry(raise_on_status=False), so 5xx never
surfaces as HTTPError. What downstream code sees is KeyError (from indexing
into stub dicts) or ValueError (from pandas DataFrame construction over
malformed payloads). _retry_and_normalize translates these to
TransientApiError so with_retries can retry on a typed signal.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.fetch import (
    fetch_calculated_metrics,
    fetch_classification_datasets,
    fetch_dimensions,
    fetch_metrics,
    fetch_segments,
    fetch_virtual_report_suites,
)
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.core.exceptions import ApiError


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch) -> AaClient:
    monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)
    handle = MagicMock()
    return AaClient(handle=handle, company_id="co", retry_policy=RetryPolicy(max_retries=3))


@pytest.mark.parametrize(
    ("fn", "sdk_method", "kwargs"),
    [
        (fetch_dimensions, "getDimensions", {"rsid": "rs1"}),
        (fetch_metrics, "getMetrics", {"rsid": "rs1"}),
        (fetch_segments, "getSegments", {"rsid": "rs1"}),
        (fetch_calculated_metrics, "getCalculatedMetrics", {"rsid": "rs1"}),
    ],
)
def test_fetcher_retries_then_succeeds(fn, sdk_method, kwargs, mock_client) -> None:
    """SDK-shape KeyError on first two attempts, success on third — fetcher
    sees TransientApiError (via _retry_and_normalize), retries, succeeds."""
    sdk_call = getattr(mock_client.handle, sdk_method)
    sdk_call.side_effect = [KeyError("content"), KeyError("content"), pd.DataFrame([])]
    result = fn(mock_client, **kwargs)
    assert sdk_call.call_count == 3
    assert result == []


def test_fetcher_exhausts_and_raises_api_error(mock_client) -> None:
    """Bubbling fetchers normalize underlying exceptions to ApiError on
    exhaustion. Note: TransientApiError IS ApiError, so pytest.raises(ApiError) catches it."""
    mock_client.handle.getDimensions.side_effect = KeyError("content")
    with pytest.raises(ApiError) as exc_info:
        fetch_dimensions(mock_client, "rs1")
    assert "KeyError" in str(exc_info.value)
    # Exhaustion: 1 initial + max_retries (3) = 4 attempts
    assert mock_client.handle.getDimensions.call_count == mock_client.retry_policy.max_retries + 1


def test_attribute_error_bubbles_as_api_error_no_retry(mock_client) -> None:
    """Non-transient bugs (AttributeError, TypeError) are NOT translated to
    TransientApiError by _classify_transient_sdk_call — they bubble through and
    are caught by the outer except-Exception, normalized to plain ApiError. No retries fire."""
    mock_client.handle.getDimensions.side_effect = AttributeError("typo")
    with pytest.raises(ApiError):
        fetch_dimensions(mock_client, "rs1")
    assert mock_client.handle.getDimensions.call_count == 1


def test_existing_api_error_passes_through_unchanged(mock_client) -> None:
    """If the underlying call raises ApiError directly, _retry_and_normalize
    passes it through without re-wrapping. Plain ApiError is non-retryable, so no retries."""
    original = ApiError("upstream said no")
    mock_client.handle.getDimensions.side_effect = original
    with pytest.raises(ApiError) as exc_info:
        fetch_dimensions(mock_client, "rs1")
    assert exc_info.value is original
    assert mock_client.handle.getDimensions.call_count == 1


def test_classifications_still_graceful_degrades_on_exhaustion(mock_client) -> None:
    """v1.0+ best-effort: exhausted classifications return FetchOutcome.degraded() (data=[]), not raise."""
    mock_client.handle.getClassificationDatasets.side_effect = KeyError("content")
    outcome = fetch_classification_datasets(mock_client, "rs1")
    assert outcome.data == []
    assert outcome.status == "degraded"
    # 1 initial + 3 retries = 4 attempts
    assert mock_client.handle.getClassificationDatasets.call_count == 4


def test_vrs_still_graceful_degrades_on_exhaustion(mock_client) -> None:
    """v1.6.1 best-effort + v1.7.0 ladder: BOTH rungs fail (full × 4 + minimal × 4) → []."""
    mock_client.handle.getVirtualReportSuites.side_effect = KeyError("content")
    result = fetch_virtual_report_suites(mock_client, "rs1")
    assert result == []
