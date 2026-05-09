"""count_only=True parameter on graceful-degrade fetchers — see spec §4.1."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from aa_auto_sdr.api.fetch import (
    fetch_classification_datasets,
    fetch_virtual_report_suites,
)


def _vrs_row(vrs_id: str, parent: str = "rs1") -> dict:
    """Minimal row shape — matches what extended_info=False returns."""
    return {"id": vrs_id, "name": vrs_id.upper(), "parentRsid": parent}


def _client_for_vrs(*, full_response=None, minimal_response=None) -> MagicMock:
    """Build a mock client where getVirtualReportSuites dispatches on extended_info."""
    handle = MagicMock()

    def get_vrs(extended_info: bool = True) -> pd.DataFrame:
        if extended_info:
            if isinstance(full_response, Exception):
                raise full_response
            return pd.DataFrame(full_response or [])
        if isinstance(minimal_response, Exception):
            raise minimal_response
        return pd.DataFrame(minimal_response or [])

    handle.getVirtualReportSuites = get_vrs
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)
    return client


def _client_for_classifications(rows: list[dict] | Exception) -> MagicMock:
    handle = MagicMock()
    if isinstance(rows, Exception):
        handle.getClassificationDatasets.side_effect = rows
    else:
        handle.getClassificationDatasets.return_value = pd.DataFrame(rows)
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)
    return client


def test_vrs_count_only_success_returns_healthy_with_stubs() -> None:
    """count_only=True succeeds → FetchOutcome.healthy with expansion_level=None.

    Verifies caller asked for minimal expansion (extended_info=False) and a
    single SDK call was made (no fallback to extended_info=True).
    """
    call_count = {"n": 0}

    def gvrs(extended_info: bool = True) -> pd.DataFrame:
        call_count["n"] += 1
        assert extended_info is False, "count_only must call extended_info=False"
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
    assert call_count["n"] == 1, "count_only must not retry to full expansion"


def test_vrs_count_only_failure_returns_degraded() -> None:
    """count_only=True fails → FetchOutcome.degraded(); no full-rung retry."""
    call_count = {"n": 0}

    def gvrs(extended_info: bool = True) -> pd.DataFrame:
        call_count["n"] += 1
        assert extended_info is False
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
    assert call_count["n"] == 1, "count_only must not fall back to extended_info=True"


def test_vrs_count_only_default_false_runs_existing_ladder() -> None:
    """count_only=False (default) runs the v1.7.0 ladder unchanged.

    Regression guard: full rung fails, minimal rung succeeds → partial(minimal).
    """
    call_log: list[bool] = []

    def gvrs(extended_info: bool = True) -> pd.DataFrame:
        call_log.append(extended_info)
        if extended_info:
            raise KeyError("content")  # full rung fails
        return pd.DataFrame([_vrs_row("v1")])  # minimal rung succeeds

    handle = MagicMock()
    handle.getVirtualReportSuites = gvrs
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)

    outcome = fetch_virtual_report_suites(client, "rs1")  # default count_only=False
    assert call_log == [True, False], "ladder must fire: full then minimal"
    assert outcome.status == "partial"
    assert outcome.expansion_level == "minimal"
    assert len(outcome.data) == 1


def test_vrs_count_only_filters_by_parent_rsid() -> None:
    """count_only=True still applies the v1.7.0 client-side parentRsid filter."""

    def gvrs(extended_info: bool = True) -> pd.DataFrame:
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
