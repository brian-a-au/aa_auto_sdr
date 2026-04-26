"""snapshot/schema.py — envelope build + validate."""

from datetime import UTC, datetime

import pytest

from aa_auto_sdr.api import models as api_models
from aa_auto_sdr.core.exceptions import SnapshotSchemaError
from aa_auto_sdr.sdr.document import SdrDocument
from aa_auto_sdr.snapshot.schema import (
    SCHEMA_VERSION,
    document_to_envelope,
    validate_envelope,
)


def _stub_doc() -> SdrDocument:
    rs = api_models.ReportSuite(
        rsid="demo.prod",
        name="Demo Production",
        timezone="UTC",
        currency="USD",
        parent_rsid=None,
    )
    return SdrDocument(
        report_suite=rs,
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 4, 26, 17, 29, 1, tzinfo=UTC),
        tool_version="0.7.0",
    )


def test_schema_version_is_v1() -> None:
    assert SCHEMA_VERSION == "aa-sdr-snapshot/v1"


def test_document_to_envelope_shape() -> None:
    env = document_to_envelope(_stub_doc())
    assert env["schema"] == SCHEMA_VERSION
    assert env["rsid"] == "demo.prod"
    assert env["captured_at"] == "2026-04-26T17:29:01+00:00"
    assert env["tool_version"] == "0.7.0"
    assert "components" in env
    assert "report_suite" in env["components"]
    assert "dimensions" in env["components"]
    # Header fields must NOT also appear nested under components
    assert "captured_at" not in env["components"]
    assert "tool_version" not in env["components"]


def test_validate_envelope_accepts_well_formed() -> None:
    env = document_to_envelope(_stub_doc())
    validate_envelope(env)  # should not raise


def test_validate_envelope_rejects_missing_schema() -> None:
    env = document_to_envelope(_stub_doc())
    del env["schema"]
    with pytest.raises(SnapshotSchemaError, match="schema"):
        validate_envelope(env)


def test_validate_envelope_rejects_unknown_major() -> None:
    env = document_to_envelope(_stub_doc())
    env["schema"] = "aa-sdr-snapshot/v999"
    with pytest.raises(SnapshotSchemaError, match="v999"):
        validate_envelope(env)


def test_validate_envelope_accepts_minor_bump() -> None:
    """v1.x is forward-compat: validate accepts v1.1, v1.2, etc."""
    env = document_to_envelope(_stub_doc())
    env["schema"] = "aa-sdr-snapshot/v1.5"
    validate_envelope(env)  # should not raise


def test_validate_envelope_rejects_missing_required_keys() -> None:
    env = document_to_envelope(_stub_doc())
    del env["rsid"]
    with pytest.raises(SnapshotSchemaError, match="rsid"):
        validate_envelope(env)


def test_validate_envelope_rejects_naive_timestamp() -> None:
    """§5.2: only timezone-aware ISO-8601 timestamps accepted."""
    env = document_to_envelope(_stub_doc())
    env["captured_at"] = "2026-04-26T17:29:01"  # no offset
    with pytest.raises(SnapshotSchemaError, match=r"naive|timezone|offset"):
        validate_envelope(env)
