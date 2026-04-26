"""Pure SDR builder: AaClient + RSID → SdrDocument.

NO I/O. Side effects belong elsewhere (output writers, snapshot store).
Component lists are sorted by ID for stable diffs."""

from __future__ import annotations

from datetime import datetime

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.sdr.document import SdrDocument


def build_sdr(
    client: AaClient,
    rsid: str,
    *,
    captured_at: datetime,
    tool_version: str,
) -> SdrDocument:
    """Fetch all components for `rsid` and assemble an SdrDocument."""
    rs = fetch.fetch_report_suite(client, rsid)
    return SdrDocument(
        report_suite=rs,
        dimensions=sorted(fetch.fetch_dimensions(client, rsid), key=lambda d: d.id),
        metrics=sorted(fetch.fetch_metrics(client, rsid), key=lambda m: m.id),
        segments=sorted(fetch.fetch_segments(client, rsid), key=lambda s: s.id),
        calculated_metrics=sorted(
            fetch.fetch_calculated_metrics(client, rsid),
            key=lambda c: c.id,
        ),
        virtual_report_suites=sorted(
            fetch.fetch_virtual_report_suites(client, rsid),
            key=lambda v: v.id,
        ),
        classifications=sorted(
            fetch.fetch_classification_datasets(client, rsid),
            key=lambda c: c.id,
        ),
        captured_at=captured_at,
        tool_version=tool_version,
    )
