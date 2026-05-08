"""Tests for api/resilience.py — RetryPolicy and retry helpers."""

from __future__ import annotations

import argparse
import dataclasses

import pytest

from aa_auto_sdr.api.resilience import DEFAULT_RETRY_POLICY, RetryPolicy


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
