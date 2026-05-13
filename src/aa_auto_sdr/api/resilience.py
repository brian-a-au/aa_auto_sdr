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
`_classify_transient_sdk_call` helper translates those to
`TransientApiError` so `is_retryable` can dispatch on a typed signal.

Worst-case total attempt count for a hard-failing endpoint at default
settings: (urllib3_retries + 1) * (max_retries + 1) = 4 * 4 = 16 HTTP
requests. With --max-retries 6, that climbs to 28. **VRS doubles this
budget** because `fetch_virtual_report_suites` runs two sequential
retry rungs (full-expansion + minimal-expansion ladder, see Item C),
each consuming the full --max-retries budget — so VRS worst case is
2 * (urllib3_retries + 1) * (max_retries + 1) = 32 at default, 56 at
--max-retries 6. Document this so operators tuning --max-retries
aren't surprised by minute-long stalls.

The helpers ``_classify_transient_sdk_call`` and ``_log_retry_attempt``
live here (not in ``api/fetch.py``) so ``api/client.py`` can use them
for the auth bootstrap retry without creating a circular import
(``api/fetch.py`` already imports ``AaClient`` from ``api/client.py``).
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from aa_auto_sdr.core.exceptions import TransientApiError, VrsEndpointShapeError

logger = logging.getLogger(__name__)

OnAttemptCb = Callable[[int, int, float, BaseException], None]


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


DEFAULT_RETRY_POLICY = RetryPolicy()


def is_retryable(exc: BaseException) -> bool:
    """True for transient failures worth retrying, False for permanent errors.

    Retryable signals (spike D1):
      - TransientApiError: typed wrapper raised by api/fetch.py's
        _retry_and_normalize for the SDK-shape failures (KeyError/ValueError
        from indexing into urllib3.Retry stub responses). Per spike: the
        aanalytics2 0.5.1 SDK never lets requests.HTTPError reach our code,
        so this typed wrapper is what we dispatch on.
      - requests.exceptions.ConnectionError / Timeout: genuine network
        failures that escape urllib3's retry budget (DNS failure, connection
        reset before any request). Always retryable.

    Non-retryable: bare KeyError/ValueError (must be classified by
    _retry_and_normalize first), plain ApiError (permanent), AuthError,
    ReportSuiteNotFoundError, AttributeError, TypeError, anything else.
    """
    return isinstance(
        exc,
        (TransientApiError, requests.exceptions.ConnectionError, requests.exceptions.Timeout),
    )


def with_retries[T](
    fn: Callable[[], T],
    *,
    policy: RetryPolicy,
    on_attempt: OnAttemptCb | None = None,
) -> T:
    """Run ``fn()`` with exponential backoff + jitter on retryable failures.

    The initial call counts as attempt 0; up to ``policy.max_retries`` retries
    follow on retryable exceptions (per :func:`is_retryable`). Total attempts
    cap at ``max_retries + 1``. On exhaustion, the last underlying exception
    bubbles unchanged — no ``RetryExhausted`` wrapper.

    ``on_attempt(attempt, max_attempts, delay_s, exc)`` fires once per RETRY
    (not the initial attempt), before the sleep. ``attempt`` ∈ [1..max_retries].
    Callback exceptions are NOT caught — a buggy logger will surface to the
    caller.
    """
    max_attempts = policy.max_retries + 1
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not is_retryable(exc) or attempt >= policy.max_retries:
                raise
            backoff = policy.base_delay * (2**attempt)
            jitter = random.uniform(0, policy.base_delay)  # noqa: S311
            delay = min(backoff + jitter, policy.max_delay)
            if on_attempt is not None:
                on_attempt(attempt + 1, max_attempts, delay, exc)
            time.sleep(delay)
    # Unreachable — the loop either returns or raises. Defensive:
    assert last_exc is not None
    raise last_exc


def classify_transient_sdk_call[T](fn: Callable[[], T], *, component_type: str | None = None) -> T:
    """Run ``fn``, classifying SDK-shape failures as ``TransientApiError``.

    Per spike (docs/superpowers/spikes/2026-05-08-aanalytics2-resilience-spike.md):
    aanalytics2 0.5.1 surfaces transient HTTP failures (5xx after urllib3
    retries, malformed bodies) as bare ``KeyError`` (from indexing into stub
    error dicts like ``vrsid['content']``) or ``ValueError`` (from pandas
    DataFrame construction over malformed payloads). This helper translates
    those to ``TransientApiError`` so ``is_retryable`` can dispatch on a
    typed signal.

    Used by ``_retry_and_normalize`` (bubbling fetchers in ``api/fetch.py``),
    the VRS ladder rungs (each rung needs the classifier independently so
    the outer try/except can fall to the next rung), AND the auth bootstrap
    in ``api/client.py``. Lives here (not ``api/fetch.py``) to avoid a
    circular import on the bootstrap path.
    """
    try:
        return fn()
    except (KeyError, ValueError) as e:
        ctx = f"{component_type} " if component_type else ""
        raise TransientApiError(f"{ctx}transient SDK failure: {type(e).__name__}: {e}") from e


def classify_permanent_vrs_shape_error[T](fn: Callable[[], T]) -> T:
    """Run ``fn``; re-raise ``KeyError('content')`` as ``VrsEndpointShapeError``.

    Wraps ``client.handle.getVirtualReportSuites`` calls inside
    ``fetch_virtual_report_suites`` (count-only, full, and minimal rungs)
    so the empty-tenant / malformed-envelope failure mode raises a
    non-transient ``ApiError`` subclass *before* the outer
    ``classify_transient_sdk_call`` promotes it to ``TransientApiError``.
    Result: the resilience layer's retry policy (``is_retryable``) skips
    the rung and the existing ``except Exception:`` falls through to the
    next rung (or to graceful-degrade), cutting ~90 s of pointless
    retries on zero-VRS tenants down to ≤ 3 s.

    See ``docs/superpowers/specs/2026-05-12-aa-auto-sdr-v1.16.1-design.md``.

    Every other exception (including other ``KeyError`` shapes and any
    ``ValueError``) bubbles unchanged so the outer classifier still gets
    the chance to promote real transients to ``TransientApiError``.
    """
    try:
        return fn()
    except KeyError as e:
        if e.args == ("content",):
            raise VrsEndpointShapeError(
                "VRS endpoint returned a malformed envelope (missing 'content' key); "
                "common on tenants with zero VRS or during Adobe-side 5xx."
            ) from e
        raise


def log_retry_attempt(
    attempt: int,
    max_attempts: int,
    delay_s: float,
    exc: BaseException,
    *,
    rsid: str | None = None,
    component_type: str | None = None,
) -> None:
    """``on_attempt`` callback for ``with_retries``. Emits a DEBUG record per retry.

    Vocabulary-compliant fields (per ``docs/LOGGING_STYLE.md`` §6.1): only
    ``retry_attempt``, ``error_class``, ``rsid``, ``component_type`` go into
    ``extra={}``. ``max_attempts`` / ``delay_s`` ride along the message string
    for human readability without being formally indexed (the structured
    sink can still parse the message if it cares).
    """
    extras: dict[str, Any] = {
        "retry_attempt": attempt,
        "error_class": type(exc).__name__,
    }
    if rsid is not None:
        extras["rsid"] = rsid
    if component_type is not None:
        extras["component_type"] = component_type
    logger.debug(
        "retry_attempt attempt=%s/%s delay_s=%.3f error_class=%s",
        attempt,
        max_attempts,
        delay_s,
        type(exc).__name__,
        extra=extras,
    )
