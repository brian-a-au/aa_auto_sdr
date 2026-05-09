"""FetchOutcome[T] / FetchStatus boundary type — see spec §4.1."""

from __future__ import annotations

import dataclasses

import pytest

from aa_auto_sdr.api import models


def test_fetch_outcome_healthy_constructor() -> None:
    out = models.FetchOutcome.healthy(["a", "b"])
    assert out.data == ["a", "b"]
    assert out.status == "healthy"
    assert out.expansion_level is None


def test_fetch_outcome_partial_constructor() -> None:
    out = models.FetchOutcome.partial(["a"], expansion_level="minimal")
    assert out.data == ["a"]
    assert out.status == "partial"
    assert out.expansion_level == "minimal"


def test_fetch_outcome_degraded_constructor() -> None:
    out = models.FetchOutcome.degraded()
    assert out.data == []
    assert out.status == "degraded"
    assert out.expansion_level is None


def test_fetch_outcome_is_frozen() -> None:
    out = models.FetchOutcome.healthy([])
    with pytest.raises(dataclasses.FrozenInstanceError):
        out.status = "partial"  # type: ignore[misc]


def test_fetch_outcome_equality() -> None:
    a = models.FetchOutcome.partial(["x"], expansion_level="reduced")
    b = models.FetchOutcome.partial(["x"], expansion_level="reduced")
    c = models.FetchOutcome.partial(["x"], expansion_level="minimal")
    assert a == b
    assert a != c


def test_fetch_status_vocabulary() -> None:
    """Status string set is closed; protect against typos in fetchers."""
    valid = {"healthy", "partial", "degraded"}
    assert {
        models.FetchOutcome.healthy([]).status,
        models.FetchOutcome.partial([], expansion_level="minimal").status,
        models.FetchOutcome.degraded().status,
    } == valid
