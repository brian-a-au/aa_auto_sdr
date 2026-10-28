"""Segment, calculated-metric, and VRS responses get the same row-shape
guard that dimensions and metrics already had.

Those three fetchers coerced the response with `_records` and then indexed
`r["id"]` outside the retry wrapper, so an SDK error stub or a row without
an id raised a bare `KeyError`. Nothing in the CLI catches `KeyError`, so a
run ended with a traceback and exit 1 instead of exit 12, and a 429 stub
never reached the retry budget.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.core.exceptions import ApiError, TransientApiError

_TRANSIENT_STUB = {"error": "Service Unavailable", "error_code": "429050"}
_RATE_LIMIT_STUB = {"error_code": "429050"}


class _FakeHandle:
    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.calls = 0

    def _respond(self, **_kwargs: Any) -> Any:
        self.calls += 1
        return self._payload

    getSegments = _respond
    getCalculatedMetrics = _respond
    getVirtualReportSuites = _respond


class _FakeClient:
    def __init__(self, payload: Any, *, max_retries: int = 0) -> None:
        self.handle = _FakeHandle(payload)
        self.retry_policy = RetryPolicy(max_retries=max_retries, base_delay=0.001, max_delay=0.001)


_ROW_FETCHERS = [
    pytest.param(fetch.fetch_segments, id="segments"),
    pytest.param(fetch.fetch_calculated_metrics, id="calculated_metrics"),
]


@pytest.mark.parametrize("fetcher", _ROW_FETCHERS)
@pytest.mark.parametrize("payload", [_TRANSIENT_STUB, _RATE_LIMIT_STUB], ids=["error_stub", "rate_limit_stub"])
def test_error_stub_is_transient_not_key_error(fetcher, payload) -> None:
    client = _FakeClient(payload)
    with pytest.raises(TransientApiError):
        fetcher(client, "rs")


@pytest.mark.parametrize("fetcher", _ROW_FETCHERS)
def test_error_stub_consumes_the_retry_budget(fetcher) -> None:
    client = _FakeClient(_TRANSIENT_STUB, max_retries=2)
    with pytest.raises(TransientApiError):
        fetcher(client, "rs")
    assert client.handle.calls == 3  # the first attempt plus two retries


@pytest.mark.parametrize("fetcher", _ROW_FETCHERS)
@pytest.mark.parametrize(
    "payload",
    [None, "bad", {"unexpected": "mapping"}, [None], [{}], [{"id": ""}], [{"id": None}], [{"id": 3}]],
    ids=["none", "string", "mapping", "null_row", "empty_row", "blank_id", "null_id", "int_id"],
)
def test_malformed_rows_are_api_errors(fetcher, payload) -> None:
    client = _FakeClient(payload)
    with pytest.raises(ApiError) as excinfo:
        fetcher(client, "rs")
    assert "rs" in str(excinfo.value)


@pytest.mark.parametrize("fetcher", _ROW_FETCHERS)
def test_well_formed_rows_still_load(fetcher) -> None:
    client = _FakeClient([{"id": "one", "name": "One"}, {"id": "two", "name": "Two"}])
    out = fetcher(client, "rs")
    assert [c.id for c in out] == ["one", "two"]


@pytest.mark.parametrize("fetcher", _ROW_FETCHERS)
def test_dataframe_responses_still_load(fetcher) -> None:
    client = _FakeClient(pd.DataFrame([{"id": "one", "name": "One"}]))
    assert [c.id for c in fetcher(client, "rs")] == ["one"]


def test_vrs_error_stub_degrades_instead_of_reporting_zero() -> None:
    """A stub must not read as a healthy empty org: `_records` wrapped the
    mapping into one row, and the parent filter then dropped it."""
    client = _FakeClient(_TRANSIENT_STUB)
    outcome = fetch.fetch_virtual_report_suites(client, "rs")
    assert outcome.status == "degraded"
    assert outcome.data == []


def test_vrs_row_without_id_is_skipped_not_fatal() -> None:
    """A VRS row with no id cannot be rendered or diffed, so it is dropped
    the same way the discovery listing drops it. The usable rows survive."""
    client = _FakeClient(
        [
            {"id": "vrs1", "name": "Good", "parentRsid": "rs"},
            {"name": "No id", "parentRsid": "rs"},
            {"id": "", "name": "Blank id", "parentRsid": "rs"},
            {"id": "vrs2", "name": "Other parent", "parentRsid": "other"},
        ],
    )
    outcome = fetch.fetch_virtual_report_suites(client, "rs")
    assert outcome.status == "healthy"
    assert [v.id for v in outcome.data] == ["vrs1"]
