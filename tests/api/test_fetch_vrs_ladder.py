"""VRS reduced-expansion ladder tests (Item C from VRS hardening spec).

LADDER APPROACH: C — two-rung (full → minimal via extended_info=False).
Per spike D2 (docs/superpowers/spikes/2026-05-08-aanalytics2-resilience-spike.md),
the SDK does not expose expansion= control, so Approach A's reduced-expansion
middle rung is not feasible without re-implementing ~40 lines of SDK internals.
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


class TestVrsLadder:
    def test_full_succeeds_no_fallback(self, mock_client) -> None:
        mock_client.handle.getVirtualReportSuites.return_value = _vrs_records()
        result = fetch_virtual_report_suites(mock_client, "rs1")
        assert result.status == "healthy"
        assert len(result.data) == 2
        # Only one SDK invocation per the happy path
        assert mock_client.handle.getVirtualReportSuites.call_count == 1

    def test_full_fails_minimal_succeeds(self, mock_client, caplog) -> None:
        """v1.16.1: KeyError('content') is classified permanent (fast-fail).
        Full-expansion fires once and falls to minimal immediately (no retry).
        Minimal-expansion succeeds first try.
        Total SDK calls: 1 (full, fast-fail) + 1 (minimal) = 2."""
        mock_client.handle.getVirtualReportSuites.side_effect = [
            KeyError("content"),  # full attempt 1 — permanent, no retry
            _vrs_records(),  # minimal attempt 1 — success
        ]
        with caplog.at_level(logging.WARNING):
            result = fetch_virtual_report_suites(mock_client, "rs1")
        assert result.status == "partial"
        assert result.expansion_level == "minimal"
        assert len(result.data) == 2
        assert mock_client.handle.getVirtualReportSuites.call_count == 2
        assert any("vrs_expansion_fallback" in r.message and "minimal" in r.message for r in caplog.records)

    def test_v1_6_1_keyerror_repro_now_returns_partial(self, mock_client, caplog) -> None:
        """Field repro: customer hit KeyError('content') from aanalytics2 0.5.1
        when Adobe's VRS endpoint returned HTTP 500. v1.6.1 returned [];
        v1.7.0 returned partial data via the minimal-expansion fallback (with retries).
        v1.16.1: KeyError('content') is classified permanent — fast-fail, no retries.
        Full fires once (permanent → no retry), minimal succeeds first try.
        Total SDK calls: 1 (full, fast-fail) + 1 (minimal) = 2."""
        mock_client.handle.getVirtualReportSuites.side_effect = [
            KeyError("content"),  # full attempt 1 — permanent, no retry
            _vrs_records(),  # minimal attempt 1 — success
        ]
        with caplog.at_level(logging.WARNING):
            result = fetch_virtual_report_suites(mock_client, "rs1")
        assert result.status == "partial"
        assert result.expansion_level == "minimal"
        assert len(result.data) == 2
        assert any("vrs_expansion_fallback" in r.message for r in caplog.records)

    def test_max_retries_zero_still_enters_ladder(self, monkeypatch, caplog) -> None:
        """Spec §5.5 resolution: --max-retries 0 disables retries but does NOT
        disable the minimal-expansion ladder. First-attempt failure on full
        triggers the minimal rung."""
        monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)
        handle = MagicMock()
        client = AaClient(handle=handle, company_id="co", retry_policy=RetryPolicy(max_retries=0))
        # Full fails immediately (no retry), minimal succeeds.
        handle.getVirtualReportSuites.side_effect = [KeyError("content"), _vrs_records()]
        with caplog.at_level(logging.WARNING):
            result = fetch_virtual_report_suites(client, "rs1")
        assert result.status == "partial"
        assert result.expansion_level == "minimal"
        assert len(result.data) == 2
        assert any("vrs_expansion_fallback" in r.message and "minimal" in r.message for r in caplog.records)

    def test_all_rungs_fail_returns_empty_preserving_v1_6_1(self, mock_client, caplog) -> None:
        """Both rungs deterministically fail → graceful-degrade to []."""
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


def test_keyerror_content_fast_fails_both_rungs(mock_client, caplog):
    """v1.16.1: KeyError('content') is now classified permanent on the VRS
    path. Both rungs fail-fast (no retries), exhaust to degraded outcome.

    Pre-1.16.1, max_retries=1 forced 2 calls per rung × 2 rungs = 4 calls.
    Post-1.16.1, fast-fail collapses to 1 call per rung = 2 calls total.

    (The additive `vrs_unavailable` WARNING is tested separately in Task 4
    so each task's commit lands with a fully green test suite.)"""
    import logging

    mock_client.handle.getVirtualReportSuites.side_effect = KeyError("content")
    with caplog.at_level(logging.WARNING):
        result = fetch_virtual_report_suites(mock_client, "rs1")
    assert result.status == "degraded"
    assert mock_client.handle.getVirtualReportSuites.call_count == 2  # one per rung, no retries
    assert any("expansion_level=exhausted" in r.message for r in caplog.records)


def test_non_content_keyerror_still_retries(mock_client):
    """Regression guard for the v1.16.1 narrow guard: KeyErrors with args
    other than ('content',) must still be promoted by the existing
    transient classifier and retried by `with_retries`. Otherwise we've
    accidentally widened the fast-fail beyond the documented shape.

    `mock_client` fixture uses RetryPolicy(max_retries=1), so a transient
    failure on the full rung fires twice (initial + 1 retry) before the
    ladder falls to the minimal rung."""
    mock_client.handle.getVirtualReportSuites.side_effect = [
        KeyError("totalElements"),  # full attempt 1 — promoted to TransientApiError
        KeyError("totalElements"),  # full attempt 2 — retry exhausts the rung
        _vrs_records(),  # minimal attempt 1 — succeeds
    ]
    result = fetch_virtual_report_suites(mock_client, "rs1")
    assert result.status == "partial"
    assert result.expansion_level == "minimal"
    assert mock_client.handle.getVirtualReportSuites.call_count == 3


def test_vrs_unavailable_warning_fires_on_shape_error_exhaust(mock_client, caplog):
    """When the cause of exhaust is the permanent shape error, an additive
    `vrs_unavailable` WARNING fires alongside the existing
    `expansion_level=exhausted` line, pointing operators at the real cause."""
    import logging

    mock_client.handle.getVirtualReportSuites.side_effect = KeyError("content")
    with caplog.at_level(logging.WARNING):
        result = fetch_virtual_report_suites(mock_client, "rs1")
    assert result.status == "degraded"
    assert any("vrs_unavailable" in r.message and "likely_cause" in r.message for r in caplog.records)
