"""resolve_rsid name_match strategies — see spec §3.3.

The existing default behavior is preserved when name_match is not passed
(case-insensitive name match). New strategies:
- exact: literal RSID match, then exact-case name match (no case-insensitive)
- insensitive: literal RSID, then case-insensitive name match (current default)
- fuzzy: literal RSID, then case-insensitive, then SequenceMatcher >= 0.85
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.api.fetch import resolve_rsid
from aa_auto_sdr.core.exceptions import (
    AmbiguousMatchError,
    ReportSuiteNotFoundError,
)


def _client_with_suites(suites: list[dict]) -> MagicMock:
    client = MagicMock()
    handle = MagicMock()
    handle.getReportSuites = MagicMock(return_value=suites)
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)
    return client


def test_exact_matches_literal_rsid() -> None:
    client = _client_with_suites([{"rsid": "rs1", "name": "Production"}])
    rsids, was_name = resolve_rsid(client, "rs1", name_match="exact")
    assert rsids == ["rs1"]
    assert was_name is False


def test_exact_matches_exact_case_name() -> None:
    client = _client_with_suites([{"rsid": "rs1", "name": "Production"}])
    rsids, was_name = resolve_rsid(client, "Production", name_match="exact")
    assert rsids == ["rs1"]
    assert was_name is True


def test_exact_no_match_on_case_variant() -> None:
    client = _client_with_suites([{"rsid": "rs1", "name": "Production"}])
    with pytest.raises(ReportSuiteNotFoundError):
        resolve_rsid(client, "production", name_match="exact")


def test_insensitive_matches_case_variant() -> None:
    client = _client_with_suites([{"rsid": "rs1", "name": "Production"}])
    rsids, was_name = resolve_rsid(client, "production", name_match="insensitive")
    assert rsids == ["rs1"]
    assert was_name is True


def test_insensitive_rsid_still_case_sensitive() -> None:
    client = _client_with_suites([{"rsid": "rs1", "name": "Production"}])
    # rsid "RS1" must NOT match "rs1" — RSIDs are case-sensitive per AA contract
    with pytest.raises(ReportSuiteNotFoundError):
        resolve_rsid(client, "RS1", name_match="insensitive")


def test_fuzzy_matches_typo() -> None:
    client = _client_with_suites([{"rsid": "rs1", "name": "lumademo"}])
    rsids, was_name = resolve_rsid(client, "lumadem", name_match="fuzzy")
    assert rsids == ["rs1"]
    assert was_name is True


def test_fuzzy_below_threshold_raises() -> None:
    client = _client_with_suites([{"rsid": "rs1", "name": "Production"}])
    with pytest.raises(ReportSuiteNotFoundError):
        resolve_rsid(client, "completely_different", name_match="fuzzy")


def test_default_preserves_existing_behavior() -> None:
    """Without name_match, behavior matches pre-v1.9.0 (case-insensitive name)."""
    client = _client_with_suites([{"rsid": "rs1", "name": "Production"}])
    rsids, _was_name = resolve_rsid(client, "production")  # default
    assert rsids == ["rs1"]


def test_no_match_raises_report_suite_not_found() -> None:
    client = _client_with_suites([{"rsid": "rs1", "name": "Production"}])
    with pytest.raises(ReportSuiteNotFoundError):
        resolve_rsid(client, "nonexistent", name_match="fuzzy")


def test_fuzzy_ambiguous_raises_ambiguous_match() -> None:
    """Two suites with similar names -> AmbiguousMatchError."""
    client = _client_with_suites(
        [
            {"rsid": "rs1", "name": "lumademo"},
            {"rsid": "rs2", "name": "lumadems"},  # both fuzz-match "lumadem" (ratio >= 0.85)
        ]
    )
    with pytest.raises(AmbiguousMatchError) as exc_info:
        resolve_rsid(client, "lumadem", name_match="fuzzy")
    assert len(exc_info.value.candidates) == 2
    assert ("rs1", "lumademo") in exc_info.value.candidates


def test_invalid_strategy_raises_value_error() -> None:
    client = _client_with_suites([])
    with pytest.raises(ValueError, match="name_match must be one of"):
        resolve_rsid(client, "anything", name_match="bogus")
