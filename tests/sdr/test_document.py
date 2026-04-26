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
