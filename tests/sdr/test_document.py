"""SdrDocument is the boundary between fetch/builder and output/snapshot."""

from datetime import UTC, datetime

from aa_auto_sdr.api import models
from aa_auto_sdr.sdr.document import SdrDocument


def _ts() -> datetime:
    return datetime(2026, 4, 25, 17, 30, tzinfo=UTC)


def test_sdr_document_holds_all_component_lists() -> None:
    rs = models.ReportSuite(
        rsid="x",
        name="X",
        timezone=None,
        currency=None,
        parent_rsid=None,
    )
    doc = SdrDocument(
        report_suite=rs,
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=_ts(),
        tool_version="0.1.0",
    )
    assert doc.report_suite == rs
    assert doc.tool_version == "0.1.0"


def test_sdr_document_to_dict_round_trip() -> None:
    rs = models.ReportSuite(
        rsid="x",
        name="X",
        timezone="UTC",
        currency="USD",
        parent_rsid=None,
    )
    dim = models.Dimension(
        id="variables/evar1",
        name="User",
        type="string",
        category="Conversion",
        parent="",
        pathable=False,
        description=None,
        tags=[],
        extra={},
    )
    doc = SdrDocument(
        report_suite=rs,
        dimensions=[dim],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=_ts(),
        tool_version="0.1.0",
    )
    d = doc.to_dict()
    assert d["report_suite"]["rsid"] == "x"
    assert d["dimensions"][0]["id"] == "variables/evar1"
    assert d["captured_at"] == "2026-04-25T17:30:00+00:00"
    assert d["tool_version"] == "0.1.0"


def _bare_rs() -> models.ReportSuite:
    return models.ReportSuite(rsid="rs1", name="RS1", timezone=None, currency=None, parent_rsid=None)


def test_to_dict_includes_quality_when_present() -> None:
    """Regression: pre-v1.12.0 SdrDocument.to_dict() silently dropped quality."""
    doc = SdrDocument(
        report_suite=_bare_rs(),
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=_ts(),
        tool_version="1.12.0",
        quality={"naming_audit": {"total_components": 0}},
    )
    payload = doc.to_dict()
    assert "quality" in payload
    assert payload["quality"] == {"naming_audit": {"total_components": 0}}


def test_to_dict_quality_none_when_no_audit() -> None:
    doc = SdrDocument(
        report_suite=_bare_rs(),
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=_ts(),
        tool_version="1.12.0",
    )
    payload = doc.to_dict()
    assert "quality" in payload
    assert payload["quality"] is None


def test_to_dict_includes_fetch_status() -> None:
    from aa_auto_sdr.sdr.document import FetchOutcomeMeta

    doc = SdrDocument(
        report_suite=_bare_rs(),
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=_ts(),
        tool_version="1.12.0",
        fetch_status={
            "virtual_report_suites": FetchOutcomeMeta(status="degraded", expansion_level="minimal"),
        },
    )
    payload = doc.to_dict()
    assert "fetch_status" in payload
    assert payload["fetch_status"]["virtual_report_suites"]["status"] == "degraded"
    assert payload["fetch_status"]["virtual_report_suites"]["expansion_level"] == "minimal"
