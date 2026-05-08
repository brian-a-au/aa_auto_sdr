"""Tests for api/resilience.py — RetryPolicy and retry helpers."""

from __future__ import annotations

import argparse
import dataclasses

import pytest
import requests

from aa_auto_sdr.api.resilience import DEFAULT_RETRY_POLICY, RetryPolicy, is_retryable
from aa_auto_sdr.core.exceptions import (
    ApiError,
    AuthError,
    ReportSuiteNotFoundError,
    TransientApiError,
)


class TestRetryPolicy:
    def test_defaults_match_v1_6_1_behavior(self) -> None:
        p = RetryPolicy()
        assert p.max_retries == 3
        assert p.base_delay == 0.5
        assert p.max_delay == 10.0

    def test_default_constant_uses_defaults(self) -> None:
        assert RetryPolicy() == DEFAULT_RETRY_POLICY

    def test_frozen(self) -> None:
        p = RetryPolicy()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.max_retries = 99  # type: ignore[misc]

    @pytest.mark.parametrize(
        ("max_retries", "base_delay", "max_delay"),
        [
            (-1, 0.5, 10.0),
            (3, 0.0, 10.0),
            (3, -0.1, 10.0),
            (3, 1.0, 0.5),  # max < base
            (3, 1.0, 0.0),
        ],
    )
    def test_validation_rejects_invalid_combinations(
        self, max_retries: int, base_delay: float, max_delay: float
    ) -> None:
        with pytest.raises(ValueError):
            RetryPolicy(max_retries=max_retries, base_delay=base_delay, max_delay=max_delay)

    def test_max_retries_zero_is_valid(self) -> None:
        p = RetryPolicy(max_retries=0, base_delay=0.5, max_delay=10.0)
        assert p.max_retries == 0

    def test_from_namespace_applies_defaults_for_none(self) -> None:
        ns = argparse.Namespace(max_retries=None, retry_base_delay=None, retry_max_delay=None)
        p = RetryPolicy.from_namespace(ns)
        assert p == RetryPolicy()

    def test_from_namespace_uses_explicit_values(self) -> None:
        ns = argparse.Namespace(max_retries=6, retry_base_delay=1.0, retry_max_delay=30.0)
        p = RetryPolicy.from_namespace(ns)
        assert p.max_retries == 6
        assert p.base_delay == 1.0
        assert p.max_delay == 30.0


class TestIsRetryable:
    def test_transient_api_error_is_retryable(self) -> None:
        """TransientApiError is the typed signal _retry_and_normalize raises
        for SDK-shape failures (KeyError/ValueError from indexing into
        urllib3.Retry stub responses, per spike D1)."""
        assert is_retryable(TransientApiError("api blew up transiently")) is True

    def test_connection_error_is_retryable(self) -> None:
        """Genuine network failures that escape urllib3's retry budget."""
        assert is_retryable(requests.exceptions.ConnectionError("boom")) is True

    def test_timeout_is_retryable(self) -> None:
        assert is_retryable(requests.exceptions.Timeout("slow")) is True

    @pytest.mark.parametrize(
        "exc",
        [
            KeyError("content"),  # raw SDK shape — must be classified by _retry_and_normalize first
            ValueError("nope"),
            ApiError("permanent api failure"),  # plain ApiError is non-retryable
            AuthError("bad token"),
            ReportSuiteNotFoundError("missing"),
            AttributeError("typo"),
            TypeError("wrong arg"),
        ],
    )
    def test_non_retryable_exception_types(self, exc: Exception) -> None:
        """Per spike D1: bare KeyError/ValueError are NOT retryable here. The
        per-call-site _retry_and_normalize helper translates them to
        TransientApiError before is_retryable sees them. Plain ApiError stays
        non-retryable so permanent API failures don't get retried."""
        assert is_retryable(exc) is False
