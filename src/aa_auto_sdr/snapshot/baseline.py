"""Covering baselines: pick the newest earlier snapshot whose scope covers a capture.

A filtered snapshot (one that left families out) sitting between two full
ones must not become the baseline of the next full capture, or changes to the
families it left out would never be compared. A candidate covers a target
when it collected every family the target collected. Snapshots without scope
(legacy files, `collected_components` absent) count as full captures, since
released versions never wrote filtered snapshots.

Pure: no I/O. Callers load envelopes and feed them newest first.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from aa_auto_sdr.sdr.document import COMPONENT_FAMILIES


def scope_of(envelope: dict[str, Any]) -> Sequence[str] | None:
    """The envelope's `collected_components`, or None when scope is unknown (legacy)."""
    return envelope.get("collected_components")


def is_full(scope: Sequence[str] | None) -> bool:
    return scope is None or set(scope) >= set(COMPONENT_FAMILIES)


def covers(candidate: Sequence[str] | None, target: Sequence[str] | None) -> bool:
    """True when a snapshot with `candidate` scope collected every family `target` did."""
    if candidate is None:
        return True
    wanted = COMPONENT_FAMILIES if target is None else target
    return set(candidate) >= set(wanted)


@dataclass(frozen=True, slots=True)
class BaselineChoice:
    """The chosen baseline envelope (None when nothing covers) and the
    `captured_at` values of newer snapshots skipped because they did not."""

    envelope: dict[str, Any] | None
    skipped: tuple[str, ...] = ()


def select_covering(
    candidates_newest_first: Iterable[dict[str, Any]],
    target_scope: Sequence[str] | None,
) -> BaselineChoice:
    """Return the first candidate whose scope covers `target_scope`.

    Consumes the iterable lazily, so callers can load history one file at a
    time and stop at the first covering snapshot."""
    skipped: list[str] = []
    for envelope in candidates_newest_first:
        if covers(scope_of(envelope), target_scope):
            return BaselineChoice(envelope=envelope, skipped=tuple(skipped))
        skipped.append(str(envelope.get("captured_at", "")))
    return BaselineChoice(envelope=None, skipped=tuple(skipped))
