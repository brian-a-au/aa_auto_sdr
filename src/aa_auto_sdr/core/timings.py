"""Lightweight timing instrumentation. Process-wide registry; off by default.

Usage:
    enable()
    with Timer("fetch"):
        client.getDimensions()
    print(report())  # -> [("fetch", 0.123)]

When disabled, Timer is a zero-cost no-op context manager."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

_records: list[tuple[str, float]] = []
_enabled: bool = False


def enable() -> None:
    """Turn on timing collection. Idempotent."""
    global _enabled  # noqa: PLW0603 — module-level toggle is the public contract
    _enabled = True


def disable() -> None:
    """Turn off timing collection. Existing records remain until clear()."""
    global _enabled  # noqa: PLW0603 — module-level toggle is the public contract
    _enabled = False


@contextmanager
def Timer(label: str) -> Iterator[None]:
    """Context manager that records elapsed seconds under `label` if enabled."""
    if not _enabled:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        _records.append((label, time.perf_counter() - start))


def report() -> list[tuple[str, float]]:
    """Return a copy of the recorded timings, in order they were captured."""
    return list(_records)


def clear() -> None:
    """Drop all recorded timings."""
    _records.clear()
