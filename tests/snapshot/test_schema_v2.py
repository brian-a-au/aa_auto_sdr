"""Snapshot envelope schema v2 — spec §4.5."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.core.exceptions import SnapshotSchemaError
from aa_auto_sdr.sdr.document import FetchOutcomeMeta, SdrDocument
from aa_auto_sdr.snapshot.schema import (
    SCHEMA_VERSION,
    document_to_envelope,
    validate_envelope,
)


def _doc(**overrides) -> SdrDocument:
    base = {
        "report_suite": models.ReportSuite(
            rsid="rs1",
            name="rs1",
            timezone=None,
            currency=None,
            parent_rsid=None,
        ),
        "dimensions": [],
        "metrics": [],
        "segments": [],
        "calculated_metrics": [],
        "virtual_report_suites": [],
        "classifications": [],
        "captured_at": datetime(2026, 5, 8, tzinfo=UTC),
        "tool_version": "1.7.1",
    }
    base.update(overrides)
    return SdrDocument(**base)


def test_schema_version_constant_bumped_to_v2() -> None:
    assert SCHEMA_VERSION == "aa-sdr-snapshot/v2"


def test_envelope_emits_v2_with_empty_status_keys_for_healthy() -> None:
    env = document_to_envelope(_doc())
    assert env["schema"] == "aa-sdr-snapshot/v2"
    assert env["degraded_components"] == []
    assert env["partial_components"] == {}


def test_envelope_partitions_fetch_status_correctly() -> None:
    doc = _doc(
        fetch_status={
            "virtual_report_suites": FetchOutcomeMeta(status="partial", expansion_level="minimal"),
            "classifications": FetchOutcomeMeta(status="degraded", expansion_level=None),
        },
    )
    env = document_to_envelope(doc)
    assert env["degraded_components"] == ["classifications"]
    assert env["partial_components"] == {"virtual_report_suites": "minimal"}


def test_envelope_keys_are_deterministic_sorted() -> None:
    """Sort-ordering keeps git-friendly diffs across snapshot files."""
    doc = _doc(
        fetch_status={
            "virtual_report_suites": FetchOutcomeMeta(status="degraded", expansion_level=None),
            "classifications": FetchOutcomeMeta(status="degraded", expansion_level=None),
        },
    )
    env = document_to_envelope(doc)
    # alphabetical
    assert env["degraded_components"] == ["classifications", "virtual_report_suites"]


def test_validate_envelope_accepts_v2() -> None:
    env = document_to_envelope(_doc())
    validate_envelope(env)  # no raise


def test_validate_envelope_rejects_v2_missing_degraded_components() -> None:
    env = document_to_envelope(_doc())
    del env["degraded_components"]
    with pytest.raises(SnapshotSchemaError, match="degraded_components"):
        validate_envelope(env)


def test_validate_envelope_rejects_v2_missing_partial_components() -> None:
    env = document_to_envelope(_doc())
    del env["partial_components"]
    with pytest.raises(SnapshotSchemaError, match="partial_components"):
        validate_envelope(env)


def test_validate_envelope_accepts_v2_minor_bump() -> None:
    """v2.x is forward-compat: validate accepts v2.1, v2.2, etc."""
    env = document_to_envelope(_doc())
    env["schema"] = "aa-sdr-snapshot/v2.1"
    validate_envelope(env)  # should not raise


def test_validate_envelope_rejects_v2_degraded_components_wrong_type() -> None:
    env = document_to_envelope(_doc())
    env["degraded_components"] = "not-a-list"
    with pytest.raises(SnapshotSchemaError, match="degraded_components must be a list"):
        validate_envelope(env)


def test_validate_envelope_rejects_v2_partial_components_wrong_type() -> None:
    env = document_to_envelope(_doc())
    env["partial_components"] = ["not-a-dict"]
    with pytest.raises(SnapshotSchemaError, match="partial_components must be a dict"):
        validate_envelope(env)
