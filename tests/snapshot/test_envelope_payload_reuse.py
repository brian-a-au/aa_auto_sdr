"""A precomputed payload is reused instead of re-serializing the document."""

from __future__ import annotations

from datetime import UTC, datetime

from aa_auto_sdr.api import models
from aa_auto_sdr.sdr.document import SdrDocument
from aa_auto_sdr.snapshot import schema


def _doc():
    rs = models.ReportSuite(rsid="rs", name="RS", timezone=None, currency=None, parent_rsid=None)
    return SdrDocument(
        report_suite=rs,
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 1, 1, tzinfo=UTC),
        tool_version="1.21.4",
    )


def test_document_to_envelope_reuses_payload(monkeypatch):
    doc = _doc()
    calls = {"n": 0}
    real = SdrDocument.to_dict

    def counting(self):
        calls["n"] += 1
        return real(self)

    monkeypatch.setattr(SdrDocument, "to_dict", counting)

    payload = doc.to_dict()  # call #1 (explicit, by the caller)
    env = schema.document_to_envelope(doc, payload=payload)
    assert env["rsid"] == "rs"
    assert calls["n"] == 1  # envelope did NOT call to_dict again
