"""build_sdr collects FetchOutcomes into SdrDocument.fetch_status — spec §4.4."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.sdr.builder import build_sdr


@pytest.fixture
def fake_client():
    """Minimal client stub; the patches below override every fetcher."""
    return object()


def _patch_fetchers(*, vrs_outcome, classifications_outcome):
    """Patch every fetcher build_sdr calls. Bubbling fetchers return [] (healthy)."""
    rs = models.ReportSuite(
        rsid="rs1",
        name="rs1",
        timezone=None,
        currency=None,
        parent_rsid=None,
    )
    return [
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_report_suite", return_value=rs),
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_dimensions", return_value=[]),
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_metrics", return_value=[]),
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_segments", return_value=[]),
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_calculated_metrics", return_value=[]),
        patch(
            "aa_auto_sdr.sdr.builder.fetch.fetch_virtual_report_suites",
            return_value=vrs_outcome,
        ),
        patch(
            "aa_auto_sdr.sdr.builder.fetch.fetch_classification_datasets",
            return_value=classifications_outcome,
        ),
    ]


def test_all_healthy_yields_empty_fetch_status(fake_client) -> None:
    patches = _patch_fetchers(
        vrs_outcome=models.FetchOutcome.healthy([]),
        classifications_outcome=models.FetchOutcome.healthy([]),
    )
    for p in patches:
        p.start()
    try:
        doc = build_sdr(
            fake_client,
            "rs1",
            captured_at=datetime(2026, 5, 8, tzinfo=UTC),
            tool_version="1.7.1",
        )
    finally:
        for p in patches:
            p.stop()
    assert doc.fetch_status == {}


def test_partial_vrs_populates_fetch_status(fake_client) -> None:
    patches = _patch_fetchers(
        vrs_outcome=models.FetchOutcome.partial([], expansion_level="minimal"),
        classifications_outcome=models.FetchOutcome.healthy([]),
    )
    for p in patches:
        p.start()
    try:
        doc = build_sdr(
            fake_client,
            "rs1",
            captured_at=datetime(2026, 5, 8, tzinfo=UTC),
            tool_version="1.7.1",
        )
    finally:
        for p in patches:
            p.stop()
    assert "virtual_report_suites" in doc.fetch_status
    assert doc.fetch_status["virtual_report_suites"].status == "partial"
    assert doc.fetch_status["virtual_report_suites"].expansion_level == "minimal"
    assert "classifications" not in doc.fetch_status


def test_degraded_classifications_populates_fetch_status(fake_client) -> None:
    patches = _patch_fetchers(
        vrs_outcome=models.FetchOutcome.healthy([]),
        classifications_outcome=models.FetchOutcome.degraded(),
    )
    for p in patches:
        p.start()
    try:
        doc = build_sdr(
            fake_client,
            "rs1",
            captured_at=datetime(2026, 5, 8, tzinfo=UTC),
            tool_version="1.7.1",
        )
    finally:
        for p in patches:
            p.stop()
    assert "classifications" in doc.fetch_status
    assert doc.fetch_status["classifications"].status == "degraded"
    assert doc.fetch_status["classifications"].expansion_level is None


def test_filtered_out_components_skip_fetch_status(fake_client) -> None:
    """ComponentFilter excludes a fetcher → no fetch_status entry, even if it would degrade."""
    from aa_auto_sdr.sdr.builder import ComponentFilter

    patches = _patch_fetchers(
        vrs_outcome=models.FetchOutcome.degraded(),  # would normally land in fetch_status
        classifications_outcome=models.FetchOutcome.degraded(),
    )
    for p in patches:
        p.start()
    try:
        doc = build_sdr(
            fake_client,
            "rs1",
            captured_at=datetime(2026, 5, 8, tzinfo=UTC),
            tool_version="1.7.1",
            component_filter=ComponentFilter(
                virtual_report_suites=False,
                classifications=False,
            ),
        )
    finally:
        for p in patches:
            p.stop()
    # Filtered-out types skip the fetch entirely; no FetchOutcome → no fetch_status entry.
    assert doc.fetch_status == {}
