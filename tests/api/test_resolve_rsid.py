"""resolve_rsid: accept either an RSID or a friendly name; resolve to one or
more canonical RSIDs. RSIDs are distinct (single match); names may match
multiple suites (cja_auto_sdr convention)."""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError


def _client_with_suites(suites: list[dict]) -> AaClient:
    handle = MagicMock()
    handle.getReportSuites.return_value = pd.DataFrame(suites)
    return AaClient(handle=handle, company_id="testco")


def test_exact_id_match_returns_single_rsid() -> None:
    client = _client_with_suites(
        [
            {"rsid": "abc.prod", "name": "Production"},
            {"rsid": "abc.dev", "name": "Development"},
        ]
    )
    rsids, was_name_lookup = fetch.resolve_rsid(client, "abc.prod")
    assert rsids == ["abc.prod"]
    assert was_name_lookup is False


def test_exact_name_match_unique_returns_single_rsid() -> None:
    client = _client_with_suites(
        [
            {"rsid": "abc.prod", "name": "Production"},
            {"rsid": "abc.dev", "name": "Development"},
        ]
    )
    rsids, was_name_lookup = fetch.resolve_rsid(client, "production")
    assert rsids == ["abc.prod"]
    assert was_name_lookup is True


def test_exact_name_match_returns_all_matching_rsids() -> None:
    """Two suites share a name. resolve_rsid returns both RSIDs, was_name_lookup=True.
    Caller (CLI) is responsible for generating an SDR per RSID — cja_auto_sdr
    convention."""
    client = _client_with_suites(
        [
            {"rsid": "abc.prod", "name": "Adobe Store"},
            {"rsid": "abc.dev", "name": "Adobe Store"},
            {"rsid": "xyz", "name": "Other"},
        ]
    )
    rsids, was_name_lookup = fetch.resolve_rsid(client, "Adobe Store")
    assert sorted(rsids) == ["abc.dev", "abc.prod"]
    assert was_name_lookup is True


def test_name_match_is_case_insensitive() -> None:
    client = _client_with_suites(
        [
            {"rsid": "abc.prod", "name": "Adobe Store"},
        ]
    )
    rsids, _ = fetch.resolve_rsid(client, "ADOBE STORE")
    assert rsids == ["abc.prod"]


def test_id_takes_precedence_over_name() -> None:
    """If a literal RSID matches another suite's name (rare), RSID wins.
    Returns single RSID, not the name-matching set."""
    client = _client_with_suites(
        [
            {"rsid": "shared", "name": "First"},
            {"rsid": "abc.prod", "name": "shared"},  # name same as another suite's rsid
        ]
    )
    rsids, was_name_lookup = fetch.resolve_rsid(client, "shared")
    assert rsids == ["shared"]  # RSID match wins; abc.prod (whose name is "shared") not included
    assert was_name_lookup is False


def test_raises_when_neither_matches() -> None:
    client = _client_with_suites(
        [
            {"rsid": "abc.prod", "name": "Production"},
        ]
    )
    with pytest.raises(ReportSuiteNotFoundError) as exc_info:
        fetch.resolve_rsid(client, "no-such-thing")
    assert "no-such-thing" in str(exc_info.value)


def test_raises_when_org_has_no_suites() -> None:
    client = _client_with_suites([])
    with pytest.raises(ReportSuiteNotFoundError):
        fetch.resolve_rsid(client, "anything")


def test_passes_extended_info_to_getReportSuites() -> None:
    """resolve_rsid should call getReportSuites(extended_info=True) so the
    response carries the name field."""
    client = _client_with_suites([{"rsid": "abc.prod", "name": "Production"}])
    fetch.resolve_rsid(client, "abc.prod")
    client.handle.getReportSuites.assert_called_once_with(extended_info=True)
