"""Tests for api/resilience.py — RetryPolicy and retry helpers."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
import requests

from aa_auto_sdr.api.resilience import (
    DEFAULT_RETRY_POLICY,
    RetryPolicy,
    is_retryable,
    with_retries,
)
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


class TestWithRetries:
    def test_succeeds_first_attempt(self) -> None:
        calls = []

        def fn() -> str:
            calls.append(1)
            return "ok"

        result = with_retries(fn, policy=RetryPolicy(max_retries=3))
        assert result == "ok"
        assert len(calls) == 1

    def test_retries_until_success(self, monkeypatch: Any) -> None:
        monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)
        calls = []

        def fn() -> str:
            calls.append(1)
            if len(calls) < 3:
                raise TransientApiError("transient")
            return "ok"

        result = with_retries(fn, policy=RetryPolicy(max_retries=3))
        assert result == "ok"
        assert len(calls) == 3

    def test_raises_last_exception_after_exhaustion(self, monkeypatch: Any) -> None:
        monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)

        def fn() -> str:
            raise TransientApiError("permanently transient")

        with pytest.raises(TransientApiError):
            with_retries(fn, policy=RetryPolicy(max_retries=2))

    def test_max_retries_zero_makes_one_attempt(self) -> None:
        calls = []

        def fn() -> str:
            calls.append(1)
            raise TransientApiError("transient")

        with pytest.raises(TransientApiError):
            with_retries(fn, policy=RetryPolicy(max_retries=0))
        assert len(calls) == 1

    def test_non_retryable_exception_raises_immediately(self) -> None:
        """Bare ValueError is non-retryable (would only become retryable after
        _retry_and_normalize translates it to TransientApiError). At the
        with_retries layer, untranslated ValueError raises on first attempt."""
        calls = []

        def fn() -> str:
            calls.append(1)
            raise ValueError("boom")

        with pytest.raises(ValueError):
            with_retries(fn, policy=RetryPolicy(max_retries=5))
        assert len(calls) == 1

    def test_on_attempt_callback_fires_per_retry(self, monkeypatch: Any) -> None:
        monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)
        attempts: list[tuple[int, int, float, str]] = []
        calls = []

        def fn() -> str:
            calls.append(1)
            if len(calls) < 3:
                raise TransientApiError("transient")
            return "ok"

        def on_attempt(attempt: int, max_attempts: int, delay_s: float, exc: BaseException) -> None:
            attempts.append((attempt, max_attempts, delay_s, type(exc).__name__))

        with_retries(fn, policy=RetryPolicy(max_retries=3), on_attempt=on_attempt)
        # Initial attempt is NOT a retry — callback fires for retries 1 and 2.
        assert len(attempts) == 2
        assert attempts[0][0] == 1  # attempt index of the retry
        assert attempts[0][1] == 4  # max_attempts = max_retries + 1
        assert attempts[1][0] == 2
        assert all(a[3] == "TransientApiError" for a in attempts)

    def test_jitter_within_bounds(self, monkeypatch: Any) -> None:
        sleeps: list[float] = []
        monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", sleeps.append)
        calls = []

        def fn() -> str:
            calls.append(1)
            if len(calls) < 5:
                raise TransientApiError("transient")
            return "ok"

        policy = RetryPolicy(max_retries=4, base_delay=1.0, max_delay=8.0)
        with_retries(fn, policy=policy)
        # 4 retries fired; each delay ∈ [base * 2^(n-1), base * 2^(n-1) + base], capped at max_delay
        assert len(sleeps) == 4
        for n, delay in enumerate(sleeps, start=1):
            backoff = 1.0 * (2 ** (n - 1))
            upper = min(backoff + 1.0, 8.0)  # jitter is uniform(0, base_delay)
            lower = min(backoff, 8.0)
            assert lower <= delay <= upper, f"retry {n}: {delay} not in [{lower}, {upper}]"


def test_vrs_endpoint_shape_error_is_apierror_not_transient() -> None:
    """VrsEndpointShapeError represents a permanent VRS endpoint shape
    failure (empty-tenant or malformed envelope from aanalytics2 0.5.1).
    It MUST be an ApiError (so `except ApiError` in fetchers catches it)
    but MUST NOT be a TransientApiError (so `is_retryable` skips it)."""
    from aa_auto_sdr.core.exceptions import ApiError, TransientApiError, VrsEndpointShapeError
    err = VrsEndpointShapeError("simulated")
    assert isinstance(err, ApiError)
    assert not isinstance(err, TransientApiError)
