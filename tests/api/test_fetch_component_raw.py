"""Exercise real SDK column selection offline with a fake read-only connector."""

from copy import deepcopy
from unittest.mock import MagicMock

import aanalytics2
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.api.fetch import fetch_dimensions, fetch_metrics
from aa_auto_sdr.core.exceptions import ApiError


def sdk_handle(rows):
    handle = object.__new__(aanalytics2.Analytics)
    handle.loggingEnabled = False
    handle.endpoint_company = "https://example.invalid/"
    handle._getDimensions = "dimensions"
    handle._getMetrics = "metrics"
    handle.header = {}
    handle.connector = MagicMock()
    handle.connector.getData.side_effect = lambda *_args, **_kwargs: deepcopy(rows)
    return handle


@pytest.mark.parametrize(("method", "fetcher"), [("getDimensions", fetch_dimensions), ("getMetrics", fetch_metrics)])
def test_actual_sdk_raw_preserves_metadata(method, fetcher):
    row = {
        "id": "component/one",
        "name": "One",
        "category": "Custom",
        "type": "string",
        "parent": "",
        "pathable": False,
        "precision": 0,
        "segmentable": True,
        "description": "Description",
        "tags": ["team"],
        "dataGroup": "Commerce",
        "standardComponent": False,
        "futureMetadata": {"value": 1},
    }
    handle = sdk_handle([row, {**row, "id": "component/two", "tags": []}])
    default = getattr(handle, method)(rsid="suite", tags=True, description=True)
    assert "tags" not in default.columns
    assert "standardComponent" not in default.columns
    components = fetcher(AaClient(handle=handle, company_id="company"), "suite")
    assert components[0].tags == ["team"]
    assert components[0].extra["standardComponent"] is False
    assert components[0].extra["futureMetadata"] == {"value": 1}
    if method == "getMetrics":
        assert components[0].data_group == "Commerce"
    assert handle.connector.getData.call_args.kwargs["params"] == {"rsid": "suite", "expansion": "tags"}


@pytest.mark.parametrize("fetcher", [fetch_dimensions, fetch_metrics])
@pytest.mark.parametrize(
    "payload", [None, {}, {"errorCode": "bad"}, "bad", [None], [{}], [{"id": ""}], [{"id": None}], [{"id": 3}]]
)
def test_malformed_raw_payload_is_contextual_api_error(fetcher, payload):
    handle = sdk_handle(payload)
    with pytest.raises(ApiError, match="suite"):
        fetcher(AaClient(handle=handle, company_id="company"), "suite")
    assert handle.connector.getData.call_count == 1


@pytest.mark.parametrize("fetcher", [fetch_dimensions, fetch_metrics])
def test_empty_raw_payload_is_healthy(fetcher):
    assert fetcher(AaClient(handle=sdk_handle([]), company_id="company"), "suite") == []


@pytest.mark.parametrize("fetcher", [fetch_dimensions, fetch_metrics])
def test_sparse_raw_metadata_preserves_unknown_and_false(fetcher):
    rows = [{"id": "one", "standardComponent": True}, {"id": "two", "standardComponent": False}, {"id": "three"}]
    components = fetcher(AaClient(handle=sdk_handle(rows), company_id="company"), "suite")
    assert components[0].extra["standardComponent"] is True
    assert components[1].extra["standardComponent"] is False
    assert "standardComponent" not in components[2].extra
    assert components[2].tags == []
    if fetcher is fetch_metrics:
        assert components[2].data_group is None


@pytest.mark.parametrize(("method", "fetcher"), [("getDimensions", fetch_dimensions), ("getMetrics", fetch_metrics)])
@pytest.mark.parametrize("stub", [{"error": "internal"}, {"error": "Request Error"}, {"error_code": "429050"}])
def test_actual_sdk_raw_error_stub_keeps_existing_retry(method, fetcher, stub, monkeypatch, caplog):
    # Characterize the former SDK path: this stub becomes a retried ValueError.
    with pytest.raises(ValueError):
        getattr(sdk_handle(stub), method)(rsid="suite")
    from aa_auto_sdr.api.resilience import RetryPolicy

    caplog.set_level("DEBUG", logger="aa_auto_sdr.api.resilience")
    monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _delay: None)
    handle = sdk_handle([])
    handle.connector.getData.side_effect = [stub, [{"id": "component/one"}]]
    client = AaClient(handle=handle, company_id="company", retry_policy=RetryPolicy(max_retries=1))
    assert fetcher(client, "suite")[0].id == "component/one"
    assert handle.connector.getData.call_count == 2
    assert len([record for record in caplog.records if "retry_attempt" in record.message]) == 1


@pytest.mark.parametrize("fetcher", [fetch_dimensions, fetch_metrics])
@pytest.mark.parametrize("max_retries", [0, 2])
def test_actual_sdk_raw_error_stub_exhausts_existing_budget(fetcher, max_retries, monkeypatch):
    from aa_auto_sdr.api.resilience import RetryPolicy
    from aa_auto_sdr.core.exceptions import TransientApiError

    monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _delay: None)
    handle = sdk_handle({"error": "internal"})
    client = AaClient(handle=handle, company_id="company", retry_policy=RetryPolicy(max_retries=max_retries))
    with pytest.raises(TransientApiError, match="suite"):
        fetcher(client, "suite")
    assert handle.connector.getData.call_count == max_retries + 1
