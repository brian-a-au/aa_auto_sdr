"""Resolution contracts exercised with both public lists and invocation indexes."""

from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.api.fetch import resolve_rsid
from aa_auto_sdr.api.report_suite_index import ReportSuiteIndex
from aa_auto_sdr.core.exceptions import AmbiguousMatchError, ReportSuiteNotFoundError


@pytest.fixture(params=[list, ReportSuiteIndex], ids=["list", "index"])
def preload(request):
    return request.param


def test_priority_order_casefold_and_ambiguity(preload):
    rows = [
        {"rsid": "z", "name": "Straße"},
        {"rsid": "a", "name": "STRASSE"},
        {"rsid": "STRASSE", "name": "Other"},
        {"rsid": "last", "name": "Straße"},
    ]
    suites = preload(rows)
    client = MagicMock()
    assert resolve_rsid(client, "STRASSE", preloaded_suites=suites) == (["STRASSE"], False)
    assert resolve_rsid(client, "strasse", preloaded_suites=suites) == (["z", "a", "last"], True)
    with pytest.raises(AmbiguousMatchError) as exc:
        resolve_rsid(client, "Straße", name_match="exact", preloaded_suites=suites)
    assert exc.value.candidates == [("z", "Straße"), ("last", "Straße")]
    with pytest.raises(AmbiguousMatchError) as exc:
        resolve_rsid(client, "strasse", name_match="fuzzy", preloaded_suites=suites)
    assert exc.value.candidates == [("z", "Straße"), ("a", "STRASSE"), ("last", "Straße")]
    client.handle.getReportSuites.assert_not_called()


@pytest.mark.parametrize("strategy", ["exact", "insensitive", "fuzzy"])
def test_unrelated_missing_id_is_lazy(preload, strategy):
    suites = preload([{"name": "Unrelated"}, {"rsid": "ok", "name": "Production"}])
    assert resolve_rsid(None, "ok", name_match=strategy, preloaded_suites=suites) == (["ok"], False)
    assert resolve_rsid(None, "Production", name_match=strategy, preloaded_suites=suites) == (["ok"], True)
    with pytest.raises(KeyError, match="rsid"):
        resolve_rsid(None, "Unrelated", name_match=strategy, preloaded_suites=suites)


def test_unhashable_values_and_string_conversion(preload):
    suites = preload([{"rsid": [], "name": []}, {"rsid": "ok", "name": {"x": 1}}])
    assert resolve_rsid(None, "[]", preloaded_suites=suites) == (["[]"], True)
    assert resolve_rsid(None, "{'x': 1}", preloaded_suites=suites) == (["ok"], True)
    with pytest.raises(ReportSuiteNotFoundError):
        resolve_rsid(None, "[]", name_match="exact", preloaded_suites=suites)


@pytest.mark.parametrize("rows", [[], [{"rsid": "one", "name": None}]])
def test_empty_and_unknown(preload, rows):
    with pytest.raises(ReportSuiteNotFoundError, match="matched neither rsid nor name"):
        resolve_rsid(None, "missing", preloaded_suites=preload(rows))


def test_fuzzy_order_and_boundary(preload):
    suites = preload([{"rsid": "z", "name": "lumademo"}, {"rsid": "a", "name": "lumadems"}])
    with pytest.raises(AmbiguousMatchError) as exc:
        resolve_rsid(None, "lumadem", name_match="fuzzy", preloaded_suites=suites)
    assert exc.value.candidates == [("z", "lumademo"), ("a", "lumadems")]
    with pytest.raises(ReportSuiteNotFoundError):
        resolve_rsid(None, "unrelated", name_match="fuzzy", preloaded_suites=suites)


def test_unrelated_rsid_is_never_stringified(preload):
    class NotText:
        def __str__(self):
            raise AssertionError("unrelated RSID was materialized")

    suites = preload([{"rsid": NotText(), "name": "Other"}, {"rsid": "ok", "name": "Production"}])
    assert resolve_rsid(None, "ok", preloaded_suites=suites) == (["ok"], False)
    assert resolve_rsid(None, "production", preloaded_suites=suites) == (["ok"], True)


def test_results_are_fresh_and_invocations_do_not_share_rows():
    first = ReportSuiteIndex([{"rsid": "one", "name": "Shared"}])
    second = ReportSuiteIndex([{"rsid": "two", "name": "Shared"}])
    result, _ = resolve_rsid(None, "shared", preloaded_suites=first)
    result.append("consumer edit")
    assert resolve_rsid(None, "shared", preloaded_suites=first) == (["one"], True)
    assert resolve_rsid(None, "shared", preloaded_suites=second) == (["two"], True)


def test_non_mapping_rows_keep_short_circuit_and_failure(preload):
    suites = preload([{"rsid": "first", "name": "First"}, None, {"rsid": "last", "name": "Last"}])
    assert resolve_rsid(None, "first", preloaded_suites=suites) == (["first"], False)
    with pytest.raises(AttributeError, match="get"):
        resolve_rsid(None, "last", preloaded_suites=suites)
