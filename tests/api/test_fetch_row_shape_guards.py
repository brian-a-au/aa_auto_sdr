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
        self.company_id = "testco"  # VrsSource binds to the client's company


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


class _ClassificationHandle:
    def __init__(self, rows: Any) -> None:
        self._rows = rows

    def getClassificationDatasets(self, **_kwargs: Any) -> Any:
        return self._rows


class _ClassificationClient:
    def __init__(self, rows: Any) -> None:
        self.handle = _ClassificationHandle(rows)
        self.retry_policy = RetryPolicy(max_retries=0, base_delay=0.001, max_delay=0.001)
        self.company_id = "testco"


def _pair(dataset: str, metric: str) -> dict[str, Any]:
    return {"dataSetId": dataset, "name": "Campaign", "rsid": "rs", "metricId": metric}


def test_classifications_are_one_row_per_dataset() -> None:
    """The endpoint is `compatibilityMetrics`, one row per dataset-and-metric
    pair. Deduping here rather than downstream keeps the count the same for
    `--describe-reportsuite`, `--stats`, `--inventory-summary`,
    `--list-classification-datasets`, and the generated SDR, which all read
    this one fetcher."""
    client = _ClassificationClient([_pair("ds1", "m1"), _pair("ds1", "m2"), _pair("ds2", "m1")])
    outcome = fetch.fetch_classification_datasets(client, "rs")
    assert [c.id for c in outcome.data] == ["ds1", "ds2"]


def test_classification_row_does_not_depend_on_response_order() -> None:
    """A key that differs between the pairs describes the pair, not the
    dataset, so keeping one row's value would make the SDR change whenever
    Adobe reorders the listing. Only the keys that agree are kept."""
    forward = _ClassificationClient([_pair("ds1", "m1"), _pair("ds1", "m2")])
    reversed_ = _ClassificationClient([_pair("ds1", "m2"), _pair("ds1", "m1")])
    first = fetch.fetch_classification_datasets(forward, "rs").data[0]
    second = fetch.fetch_classification_datasets(reversed_, "rs").data[0]
    assert first == second
    assert "metricId" not in first.extra


def test_classification_keys_shared_by_every_pair_are_kept() -> None:
    rows = [
        {**_pair("ds1", "m1"), "owner": "team-a"},
        {**_pair("ds1", "m2"), "owner": "team-a"},
    ]
    dataset = fetch.fetch_classification_datasets(_ClassificationClient(rows), "rs").data[0]
    assert dataset.extra["owner"] == "team-a"


def test_single_classification_row_keeps_every_key() -> None:
    rows = [{**_pair("ds1", "m1"), "owner": "team-a"}]
    dataset = fetch.fetch_classification_datasets(_ClassificationClient(rows), "rs").data[0]
    assert dataset.extra == {"metricId": "m1", "owner": "team-a"}


def test_vrs_error_stub_degrades_instead_of_reporting_zero() -> None:
    """A stub must not read as a healthy empty org: `_records` wrapped the
    mapping into one row, and the parent filter then dropped it."""
    client = _FakeClient(_TRANSIENT_STUB)
    outcome = fetch.fetch_virtual_report_suites(client, "rs")
    assert outcome.status == "degraded"
    assert outcome.data == []


def test_vrs_row_without_id_is_skipped_not_fatal() -> None:
    """A VRS row with no usable id cannot be rendered or diffed, so it is
    dropped. The usable rows survive."""
    client = _FakeClient(
        [
            {"id": "vrs1", "name": "Good", "parentRsid": "rs"},
            {"name": "No id", "parentRsid": "rs"},
            {"id": "", "name": "Blank id", "parentRsid": "rs"},
            {"id": float("nan"), "name": "NaN id", "parentRsid": "rs"},
            {"id": "vrs2", "name": "Other parent", "parentRsid": "other"},
        ],
    )
    outcome = fetch.fetch_virtual_report_suites(client, "rs")
    assert outcome.status == "healthy"
    assert [v.id for v in outcome.data] == ["vrs1"]


def test_vrs_non_string_id_is_kept_and_coerced() -> None:
    """A DataFrame conversion can hand back a numeric id. The discovery
    listing keeps such a row, so the generated SDR must keep it too rather
    than quietly holding fewer VRS than `--list-virtual-reportsuites`."""
    client = _FakeClient([{"id": 7, "name": "Numeric", "parentRsid": "rs"}])
    outcome = fetch.fetch_virtual_report_suites(client, "rs")
    assert [v.id for v in outcome.data] == ["7"]


@pytest.mark.parametrize("shared", [False, True], ids=["per_rsid", "shared_source"])
def test_vrs_skipped_rows_do_not_skew_the_parent_filter_record(shared, caplog) -> None:
    """The `vrs_parent_filter` record's arithmetic is
    `pulled - filtered - dropped_no_parent = dropped_other_parent`. Rows
    dropped for an unusable id must not land in `dropped_other_parent`, or
    the record blames the parent filter for them. On the shared-source path
    the counts came from the unfiltered listing, so they did."""
    import logging

    from aa_auto_sdr.api.vrs_source import VrsSource

    client = _FakeClient(
        [
            {"id": "vrs1", "name": "Good", "parentRsid": "rs"},
            {"name": "No id", "parentRsid": "rs"},
            {"id": "vrs2", "name": "Other parent", "parentRsid": "other"},
            {"id": "vrs3", "name": "No parent", "parentRsid": ""},
        ],
    )
    source = VrsSource(client) if shared else None
    with caplog.at_level(logging.DEBUG, logger="aa_auto_sdr.api.fetch"):
        outcome = fetch.fetch_virtual_report_suites(client, "rs", source=source)
    assert [v.id for v in outcome.data] == ["vrs1"]
    records = [r for r in caplog.records if r.msg.startswith("vrs_parent_filter")]
    assert len(records) == 1
    record = records[0]
    assert record.pulled - record.filtered - record.dropped_no_parent == record.dropped_other_parent
    assert record.dropped_other_parent == 1  # vrs2 only, not the id-less row
