"""Coverage for small coercion helpers and a defensive error path in api/fetch.py.

Covers _records (None / dict shapes), _int (non-coercible value), _list
(scalar wrap), resolve_rsid's fuzzy-fallback None-name skip, and the
fetch_virtual_report_suite_summaries non-ApiError normalization branch.
"""

from __future__ import annotations

import logging as _logging
from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core.exceptions import ApiError, ReportSuiteNotFoundError


def test_records_returns_empty_list_for_none() -> None:
    assert fetch._records(None) == []


def test_records_wraps_single_dict() -> None:
    assert fetch._records({"a": 1}) == [{"a": 1}]


def test_int_returns_default_on_non_coercible_value() -> None:
    # str that isn't a number → ValueError → default.
    assert fetch._int({"k": "not-an-int"}, "k") == 0
    # list → TypeError → default (explicit non-zero default to prove the path).
    assert fetch._int({"k": []}, "k", default=7) == 7


def test_list_wraps_scalar_value() -> None:
    assert fetch._list({"k": "scalar"}, "k") == ["scalar"]


def test_resolve_rsid_fuzzy_skips_suites_with_none_name() -> None:
    """A suite whose `name` is None must be skipped during the fuzzy fallback
    rather than raising. Use a plain list (not a DataFrame) so None stays None
    instead of becoming NaN after to_dict()."""
    handle = MagicMock()
    handle.getReportSuites.return_value = [
        {"rsid": "rs1", "name": None},
        {"rsid": "rs2", "name": "Completely Different"},
    ]
    client = AaClient(handle=handle, company_id="testco")

    with pytest.raises(ReportSuiteNotFoundError):
        fetch.resolve_rsid(client, "zzzz-no-match", name_match="fuzzy")


def test_vrs_summaries_normalizes_non_apierror_to_apierror(caplog: pytest.LogCaptureFixture) -> None:
    """A non-(KeyError/ValueError), non-ApiError SDK failure (e.g. RuntimeError)
    escapes with_retries unclassified; the discovery fetcher must wrap it as a
    plain ApiError and emit a DEBUG record."""
    caplog.set_level(_logging.DEBUG, logger="aa_auto_sdr.api.fetch")
    handle = MagicMock()
    handle.getVirtualReportSuites.side_effect = RuntimeError("boom")
    client = AaClient(handle=handle, company_id="testco")

    with pytest.raises(ApiError, match="RuntimeError"):
        fetch.fetch_virtual_report_suite_summaries(client)

    assert any("virtual report suites fetch failed" in r.getMessage() for r in caplog.records)
