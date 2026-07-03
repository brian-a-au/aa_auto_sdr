"""count_only=True parameter on graceful-degrade fetchers — see spec §4.1.

count_only requests FULL expansion: the SDK's extended_info=False path strips
rows to {name, vrsid} — no parentRsid — so a reduced-expansion call cannot
support the client-side parent filter and reported 0 VRS for every org.
count_only's remaining contract is the single call and the healthy/degraded
outcome shape.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from aa_auto_sdr.api.fetch import (
    fetch_classification_datasets,
    fetch_virtual_report_suites,
)


def _vrs_row(vrs_id: str, parent: str = "rs1") -> dict:
    """Full-expansion row shape — id + parentRsid present."""
    return {"id": vrs_id, "name": vrs_id.upper(), "parentRsid": parent}


def test_vrs_count_only_success_returns_healthy_with_stubs() -> None:
    """count_only=True succeeds → FetchOutcome.healthy with expansion_level=None.

    Verifies the caller asked for full expansion (extended_info=True — the
    reduced shape has no parentRsid, so counts would be structurally zero)
    and that a single SDK call was made."""
    call_count = {"n": 0}

    def gvrs(extended_info: bool = False, limit: int = 100) -> pd.DataFrame:
        call_count["n"] += 1
        assert extended_info is True, "count_only must request full expansion"
        return pd.DataFrame([_vrs_row("v1")])

    handle = MagicMock()
    handle.getVirtualReportSuites = gvrs
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)

    outcome = fetch_virtual_report_suites(client, "rs1", count_only=True)
    assert outcome.status == "healthy"
    assert outcome.expansion_level is None
    assert len(outcome.data) == 1
    assert outcome.data[0].id == "v1"
    assert call_count["n"] == 1, "count_only must be a single SDK call"


def test_vrs_count_only_failure_returns_degraded() -> None:
    """count_only=True fails → FetchOutcome.degraded() after one call."""
    call_count = {"n": 0}

    def gvrs(extended_info: bool = False, limit: int = 100) -> pd.DataFrame:
        call_count["n"] += 1
        raise KeyError("content")

    handle = MagicMock()
    handle.getVirtualReportSuites = gvrs
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)

    outcome = fetch_virtual_report_suites(client, "rs1", count_only=True)
    assert outcome.status == "degraded"
    assert outcome.expansion_level is None
    assert outcome.data == []
    assert call_count["n"] == 1


def test_vrs_count_only_default_false_same_single_rung() -> None:
    """count_only=False (default) runs the same single full-expansion rung:
    a failure degrades directly — no reduced-expansion fallback call."""
    call_log: list[bool] = []

    def gvrs(extended_info: bool = False, limit: int = 100) -> pd.DataFrame:
        call_log.append(extended_info)
        raise KeyError("content")

    handle = MagicMock()
    handle.getVirtualReportSuites = gvrs
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)

    outcome = fetch_virtual_report_suites(client, "rs1")  # default count_only=False
    assert call_log == [True], "single full-expansion call, no fallback"
    assert outcome.status == "degraded"
    assert outcome.data == []


def test_vrs_count_only_filters_by_parent_rsid() -> None:
    """count_only=True still applies the v1.7.0 client-side parentRsid filter."""

    def gvrs(extended_info: bool = False, limit: int = 100) -> pd.DataFrame:
        # Two rows: one matching the requested parent, one belonging to a different parent.
        return pd.DataFrame(
            [
                _vrs_row("v1", parent="rs1"),
                _vrs_row("v2", parent="rs999"),
            ]
        )

    handle = MagicMock()
    handle.getVirtualReportSuites = gvrs
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)

    outcome = fetch_virtual_report_suites(client, "rs1", count_only=True)
    assert outcome.status == "healthy"
    assert len(outcome.data) == 1
    assert outcome.data[0].id == "v1"


def test_classifications_count_only_is_noop_on_success() -> None:
    """count_only=True for classifications behaves identically to count_only=False."""
    handle = MagicMock()
    handle.getClassificationDatasets.return_value = pd.DataFrame(
        [{"id": "ds1", "name": "Marketing"}],
    )
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)

    out_with = fetch_classification_datasets(client, "rs1", count_only=True)
    out_without = fetch_classification_datasets(client, "rs1", count_only=False)
    assert out_with.status == out_without.status == "healthy"
    assert len(out_with.data) == len(out_without.data) == 1
    assert out_with.data[0].id == out_without.data[0].id == "ds1"


def test_classifications_count_only_is_noop_on_failure() -> None:
    """count_only=True for classifications still graceful-degrades on SDK exception."""
    handle = MagicMock()
    handle.getClassificationDatasets.side_effect = KeyError("content")
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)

    outcome = fetch_classification_datasets(client, "rs1", count_only=True)
    assert outcome.status == "degraded"
    assert outcome.data == []


def test_count_only_keyerror_content_fast_fails(monkeypatch, caplog) -> None:
    """v1.16.1: count-only path also fast-fails on KeyError('content')
    and emits the additive vrs_unavailable warning."""
    import logging

    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.resilience import RetryPolicy

    monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)
    handle = MagicMock()
    handle.getVirtualReportSuites.side_effect = KeyError("content")
    client = AaClient(handle=handle, company_id="co", retry_policy=RetryPolicy(max_retries=1))

    with caplog.at_level(logging.WARNING):
        result = fetch_virtual_report_suites(client, "rs1", count_only=True)

    assert result.status == "degraded"
    # No retries — count-only does a single SDK call when shape-error fires
    assert handle.getVirtualReportSuites.call_count == 1
    assert any("vrs_unavailable" in r.message for r in caplog.records)
    assert any("expansion_level=count_only" in r.message for r in caplog.records)
