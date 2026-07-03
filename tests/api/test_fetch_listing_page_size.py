"""Listing calls page at the API maximum (limit=1000), not the SDK default (100).

The aanalytics2 SDK paginates getReportSuites / getVirtualReportSuites
internally at `limit` rows per HTTP request, defaulting to 100. Passing the
API max cuts listing round-trips ~10x for large orgs; the server clamps and
`totalPages`/`lastPage` still drive pagination, so a lower server cap is safe.
Mirrors the v1.21.4 change that moved segments / calculated metrics to
limit=1000.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient


def _client(rs_rows: list[dict] | None = None, vrs_rows: list[dict] | None = None) -> AaClient:
    handle = MagicMock()
    handle.getReportSuites.return_value = pd.DataFrame(
        rs_rows or [{"rsid": "demo.prod", "name": "Demo"}],
    )
    handle.getVirtualReportSuites.return_value = pd.DataFrame(
        vrs_rows or [{"id": "vrs.a", "name": "A", "parentRsid": "demo.prod"}],
    )
    return AaClient(handle=handle, company_id="testco")


def test_fetch_report_suite_pages_at_api_max() -> None:
    client = _client()
    fetch.fetch_report_suite(client, "demo.prod")
    _, kwargs = client.handle.getReportSuites.call_args
    assert kwargs.get("limit") == 1000


def test_fetch_report_suite_summaries_pages_at_api_max() -> None:
    client = _client()
    fetch.fetch_report_suite_summaries(client)
    _, kwargs = client.handle.getReportSuites.call_args
    assert kwargs.get("limit") == 1000


def test_fetch_report_suites_raw_pages_at_api_max() -> None:
    client = _client()
    fetch.fetch_report_suites_raw(client)
    _, kwargs = client.handle.getReportSuites.call_args
    assert kwargs.get("limit") == 1000


def test_resolve_rsid_listing_pages_at_api_max() -> None:
    client = _client()
    fetch.resolve_rsid(client, "demo.prod")
    _, kwargs = client.handle.getReportSuites.call_args
    assert kwargs.get("limit") == 1000


def test_fetch_virtual_report_suites_pages_at_api_max() -> None:
    client = _client()
    fetch.fetch_virtual_report_suites(client, "demo.prod")
    _, kwargs = client.handle.getVirtualReportSuites.call_args
    assert kwargs.get("limit") == 1000


def test_fetch_virtual_report_suite_summaries_pages_at_api_max() -> None:
    client = _client()
    fetch.fetch_virtual_report_suite_summaries(client)
    _, kwargs = client.handle.getVirtualReportSuites.call_args
    assert kwargs.get("limit") == 1000
