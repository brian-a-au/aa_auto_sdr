"""VRS fetch resilience tests — single full-expansion rung.

Historical note: v1.7.0 ran a two-rung ladder (full → minimal via
extended_info=False). The ladder was retired when the minimal rung was shown
to be structurally empty: the SDK strips reduced-expansion rows to
{name, vrsid} — no parentRsid — so the client-side parent filter dropped
every row and the rung could only ever return partial([]) after burning a
second full retry budget. Failure of the full rung now degrades directly.
See tests/api/test_fetch_vrs_full_expansion_only.py for the truthful-shape
regression tests.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.fetch import fetch_virtual_report_suites
from aa_auto_sdr.api.resilience import RetryPolicy


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch) -> AaClient:
    monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)
    handle = MagicMock()
    return AaClient(handle=handle, company_id="co", retry_policy=RetryPolicy(max_retries=1))


def _vrs_records(parent: str = "rs1") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"id": "vrs_1", "name": "VRS One", "parentRsid": parent},
            {"id": "vrs_2", "name": "VRS Two", "parentRsid": parent},
        ]
    )


class TestVrsSingleRung:
    def test_full_succeeds_single_call(self, mock_client) -> None:
        mock_client.handle.getVirtualReportSuites.return_value = _vrs_records()
        result = fetch_virtual_report_suites(mock_client, "rs1")
        assert result.status == "healthy"
        assert len(result.data) == 2
        # Only one SDK invocation per the happy path
        assert mock_client.handle.getVirtualReportSuites.call_count == 1

    def test_keyerror_content_degrades_in_one_call(self, mock_client, caplog) -> None:
        """Field repro: customer hit KeyError('content') from aanalytics2 0.5.1
        when Adobe's VRS endpoint returned HTTP 500. v1.16.1 classifies it
        permanent — fast-fail, no retries. With the minimal fallback rung
        retired, the single full-rung failure degrades directly:
        1 SDK call total, no reduced-expansion attempt."""
        mock_client.handle.getVirtualReportSuites.side_effect = KeyError("content")
        with caplog.at_level(logging.WARNING):
            result = fetch_virtual_report_suites(mock_client, "rs1")
        assert result.status == "degraded"
        assert result.data == []
        assert mock_client.handle.getVirtualReportSuites.call_count == 1
        assert not any("vrs_expansion_fallback" in r.message for r in caplog.records)

    def test_max_retries_zero_single_attempt(self, monkeypatch, caplog) -> None:
        """--max-retries 0 disables retries; a first-attempt failure on the
        full rung degrades with exactly one SDK call."""
        monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)
        handle = MagicMock()
        client = AaClient(handle=handle, company_id="co", retry_policy=RetryPolicy(max_retries=0))
        handle.getVirtualReportSuites.side_effect = KeyError("content")
        with caplog.at_level(logging.WARNING):
            result = fetch_virtual_report_suites(client, "rs1")
        assert result.status == "degraded"
        assert handle.getVirtualReportSuites.call_count == 1

    def test_full_rung_fail_returns_empty_preserving_v1_6_1(self, mock_client, caplog) -> None:
        """Deterministic failure → graceful-degrade to [] (v1.6.1 contract)."""
        mock_client.handle.getVirtualReportSuites.side_effect = KeyError("content")
        with caplog.at_level(logging.WARNING):
            result = fetch_virtual_report_suites(mock_client, "rs1")
        assert result.status == "degraded"
        assert result.data == []
        assert any("virtual report suites fetch failed" in r.message for r in caplog.records)

    def test_expansion_level_field_on_component_fetch_info(self, mock_client, caplog) -> None:
        mock_client.handle.getVirtualReportSuites.return_value = _vrs_records()
        with caplog.at_level(logging.INFO):
            fetch_virtual_report_suites(mock_client, "rs1")
        info_records = [
            r for r in caplog.records if "component_fetch" in r.message and "virtual_report_suite" in r.message
        ]
        assert info_records, "Expected component_fetch INFO record"
        assert getattr(info_records[0], "expansion_level", None) == "full"


def test_keyerror_content_fast_fails_without_retries(mock_client, caplog):
    """v1.16.1: KeyError('content') is classified permanent on the VRS path —
    fail-fast, no retries. One rung → exactly 1 SDK call, exhausted label."""
    mock_client.handle.getVirtualReportSuites.side_effect = KeyError("content")
    with caplog.at_level(logging.WARNING):
        result = fetch_virtual_report_suites(mock_client, "rs1")
    assert result.status == "degraded"
    assert mock_client.handle.getVirtualReportSuites.call_count == 1  # no retries, no second rung
    assert any("expansion_level=exhausted" in r.message for r in caplog.records)


def test_non_content_keyerror_still_retries(mock_client):
    """Regression guard for the v1.16.1 narrow guard: KeyErrors with args
    other than ('content',) must still be promoted by the existing
    transient classifier and retried by `with_retries`. Otherwise we've
    accidentally widened the fast-fail beyond the documented shape.

    `mock_client` fixture uses RetryPolicy(max_retries=1): initial + 1 retry
    on the single full rung, then degraded."""
    mock_client.handle.getVirtualReportSuites.side_effect = [
        KeyError("totalElements"),  # attempt 1 — promoted to TransientApiError
        KeyError("totalElements"),  # attempt 2 — retry exhausts the budget
    ]
    result = fetch_virtual_report_suites(mock_client, "rs1")
    assert result.status == "degraded"
    assert mock_client.handle.getVirtualReportSuites.call_count == 2


def test_vrs_unavailable_warning_fires_on_shape_error_exhaust(mock_client, caplog):
    """When the cause of exhaust is the permanent shape error, an additive
    `vrs_unavailable` WARNING fires alongside the existing
    `expansion_level=exhausted` line, pointing operators at the real cause."""
    mock_client.handle.getVirtualReportSuites.side_effect = KeyError("content")
    with caplog.at_level(logging.WARNING):
        result = fetch_virtual_report_suites(mock_client, "rs1")
    assert result.status == "degraded"
    assert any("vrs_unavailable" in r.message and "likely_cause" in r.message for r in caplog.records)
