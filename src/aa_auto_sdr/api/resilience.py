"""Retry-with-jitter helpers for AA SDK calls.

Per CLAUDE.md: "Retry-with-jitter only at first; no circuit breaker yet."
This module deliberately does not implement circuit-breaker shapes
(failure-rate tracking, cooldown, half-open states). Adding those requires
a new spec.

The retry layer composes with aanalytics2's internal urllib3 retries — it
runs OUTSIDE the SDK call. Per the 2026-05-08 spike, aanalytics2 0.5.1
configures urllib3.Retry(total=max(max_retries, 3), backoff_factor=1,
status_forcelist=[429, 500, 502, 503, 504], raise_on_status=False).
A 5xx that exhausts urllib3's budget surfaces as a swallowed stub dict,
which the SDK then indexes into and raises KeyError/ValueError. The
`_retry_and_normalize` helper in `api/fetch.py` translates those to
`TransientApiError` so `is_retryable` can dispatch on a typed signal.

Worst-case total attempt count for a hard-failing endpoint at default
settings: (urllib3_retries + 1) * (max_retries + 1) = 4 * 4 = 16 HTTP
requests. With --max-retries 6, that climbs to 28. Document this so
operators tuning --max-retries aren't surprised by minute-long stalls.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    """Retry budget + exponential-backoff parameters."""

    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 10.0

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be non-negative, got {self.max_retries}")
        if self.base_delay <= 0:
            raise ValueError(f"base_delay must be positive, got {self.base_delay}")
        if self.max_delay < self.base_delay:
            raise ValueError(f"max_delay ({self.max_delay}) must be >= base_delay ({self.base_delay})")

    # Wired up by Task 4 (CLI flags --max-retries / --retry-base-delay /
    # --retry-max-delay) in the v1.7.0 plan; resolution lives in cli/main.run().
    @classmethod
    def from_namespace(cls, ns: argparse.Namespace) -> RetryPolicy:
        """Build a policy from parsed CLI args. None values get defaults."""
        defaults = cls()
        return cls(
            max_retries=ns.max_retries if ns.max_retries is not None else defaults.max_retries,
            base_delay=(ns.retry_base_delay if ns.retry_base_delay is not None else defaults.base_delay),
            max_delay=(ns.retry_max_delay if ns.retry_max_delay is not None else defaults.max_delay),
        )


DEFAULT_RETRY_POLICY = RetryPolicy()
