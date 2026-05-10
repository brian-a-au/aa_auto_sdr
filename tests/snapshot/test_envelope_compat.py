"""v3 envelope: optional top-level `quality` field.

See spec §3.5–§3.6.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aa_auto_sdr.api.models import ReportSuite
from aa_auto_sdr.sdr.document import SdrDocument
from aa_auto_sdr.snapshot.schema import (
    SCHEMA_VERSION,
    document_to_envelope,
    validate_envelope,
)


def _doc(quality: dict | None = None) -> SdrDocument:
    return SdrDocument(
        report_suite=ReportSuite(
            rsid="rs1",
            name="Test",
            timezone="UTC",
            currency=None,
            parent_rsid=None,
        ),
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 5, 9, tzinfo=UTC),
        tool_version="1.9.0",
        quality=quality,
    )


def test_schema_version_is_v4() -> None:
    assert SCHEMA_VERSION == "aa-sdr-snapshot/v4"


def test_envelope_has_quality_key_when_set() -> None:
    doc = _doc(quality={"naming_audit": {"total_components": 3}})
    env = document_to_envelope(doc)
    assert env["quality"] == {"naming_audit": {"total_components": 3}}


def test_envelope_quality_key_present_as_none_when_unset() -> None:
    """v3 envelopes carry `quality` even when None — easier for downstream readers."""
    doc = _doc(quality=None)
    env = document_to_envelope(doc)
    assert "quality" in env
    assert env["quality"] is None


def test_envelope_quality_inside_top_level_not_components() -> None:
    """Promoted out, alongside degraded_components/partial_components."""
    doc = _doc(quality={"naming_audit": {}})
    env = document_to_envelope(doc)
    assert "quality" not in env["components"]


def test_validate_v3_envelope_with_quality() -> None:
    """v3 envelope with quality validates."""
    env = {
        "schema": "aa-sdr-snapshot/v3",
        "rsid": "rs1",
        "captured_at": "2026-05-09T00:00:00+00:00",
        "tool_version": "1.9.0",
        "degraded_components": [],
        "partial_components": {},
        "quality": {"naming_audit": {"total_components": 0}},
        "components": {},
    }
    validate_envelope(env)  # no raise


def test_validate_v3_envelope_quality_omitted_defaults_to_none() -> None:
    """Forward-compat: v3 envelope missing `quality` is read as None."""
    env = {
        "schema": "aa-sdr-snapshot/v3",
        "rsid": "rs1",
        "captured_at": "2026-05-09T00:00:00+00:00",
        "tool_version": "1.9.0",
        "degraded_components": [],
        "partial_components": {},
        "components": {},
    }
    validate_envelope(env)
    assert env["quality"] is None


def test_validate_v2_envelope_still_passes_with_no_quality() -> None:
    """Backward compat: v2 envelopes without quality keep validating."""
    env = {
        "schema": "aa-sdr-snapshot/v2",
        "rsid": "rs1",
        "captured_at": "2026-05-09T00:00:00+00:00",
        "tool_version": "1.8.0",
        "degraded_components": [],
        "partial_components": {},
        "components": {},
    }
    validate_envelope(env)
    # v2 envelopes don't have quality at all; reader should default it.
    assert env.get("quality") is None


def test_validate_v1_envelope_still_passes() -> None:
    """Backward compat: v1 envelopes (predating v2 keys) still validate."""
    env = {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": "rs1",
        "captured_at": "2026-05-09T00:00:00+00:00",
        "tool_version": "1.6.0",
        "components": {},
    }
    validate_envelope(env)


def test_validate_unsupported_schema_raises() -> None:
    """Schema v5 is not yet supported — should raise."""
    from aa_auto_sdr.core.exceptions import SnapshotSchemaError

    env = {
        "schema": "aa-sdr-snapshot/v5",
        "rsid": "rs1",
        "captured_at": "2026-05-09T00:00:00+00:00",
        "tool_version": "2.0.0",
        "components": {},
    }
    with pytest.raises(SnapshotSchemaError):
        validate_envelope(env)
