"""SdrDocument.fetch_status field shape — see spec §4.3."""

from __future__ import annotations

from datetime import UTC, datetime

from aa_auto_sdr.api import models
from aa_auto_sdr.sdr.document import FetchOutcomeMeta, SdrDocument


def _make_doc(**overrides) -> SdrDocument:
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


def test_fetch_status_defaults_to_empty_dict() -> None:
    doc = _make_doc()
    assert doc.fetch_status == {}


def test_to_dict_emits_fetch_status() -> None:
    """v1.12.0 fix: SdrDocument.to_dict() now includes fetch_status.

    Pre-v1.12.0 the field was deliberately excluded from to_dict() so
    user-facing JSON stayed clean. v1.12.0 reverses that: fetch_status
    is part of the document boundary and downstream consumers benefit
    from seeing degraded/partial outcomes in the JSON output.
    snapshot/schema.py still partitions it into top-level
    degraded_components/partial_components keys (popped from the nested
    components payload to avoid duplication).
    """
    doc = _make_doc(
        fetch_status={
            "virtual_report_suites": FetchOutcomeMeta(
                status="partial",
                expansion_level="minimal",
            ),
        },
    )
    payload = doc.to_dict()
    assert "fetch_status" in payload
    assert payload["fetch_status"]["virtual_report_suites"]["status"] == "partial"


def test_fetch_status_uses_plural_envelope_keys() -> None:
    """Map keys must match snapshot/comparator.py::_COMPONENT_TYPES (plural)."""
    doc = _make_doc(
        fetch_status={
            "virtual_report_suites": FetchOutcomeMeta(status="degraded", expansion_level=None),
        },
    )
    assert "virtual_report_suite" not in doc.fetch_status  # singular form rejected by convention
    assert "virtual_report_suites" in doc.fetch_status
