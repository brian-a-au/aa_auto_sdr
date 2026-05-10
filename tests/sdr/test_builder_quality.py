"""build_sdr quality kwargs: audit_naming + flag_stale.

See spec §3.7.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.api.models import (
    Dimension,
    FetchOutcome,
    ReportSuite,
)
from aa_auto_sdr.sdr.builder import build_sdr


@pytest.fixture
def fake_client() -> MagicMock:
    return MagicMock()


def _patch_fetchers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub all fetchers in sdr/builder so build_sdr returns a known bundle.

    Two of the dimensions are designed to trigger detect_stale (`old_thing`)
    and contribute to audit_naming (`old_thing` and `customer_id`).
    """
    rs = ReportSuite(
        rsid="rs1",
        name="Test",
        timezone="UTC",
        currency=None,
        parent_rsid=None,
    )
    monkeypatch.setattr("aa_auto_sdr.sdr.builder.fetch.fetch_report_suite", lambda _c, _r: rs)
    monkeypatch.setattr(
        "aa_auto_sdr.sdr.builder.fetch.fetch_dimensions",
        lambda _c, _r: [
            Dimension(
                id="evar1",
                name="old_thing",  # triggers stale
                type="string",
                category=None,
                parent="",
                pathable=False,
                description=None,
            ),
            Dimension(
                id="evar2",
                name="customer_id",  # clean
                type="string",
                category=None,
                parent="",
                pathable=False,
                description=None,
            ),
        ],
    )
    monkeypatch.setattr("aa_auto_sdr.sdr.builder.fetch.fetch_metrics", lambda _c, _r: [])
    monkeypatch.setattr("aa_auto_sdr.sdr.builder.fetch.fetch_segments", lambda _c, _r: [])
    monkeypatch.setattr("aa_auto_sdr.sdr.builder.fetch.fetch_calculated_metrics", lambda _c, _r: [])
    monkeypatch.setattr(
        "aa_auto_sdr.sdr.builder.fetch.fetch_virtual_report_suites",
        lambda _c, _r: FetchOutcome.healthy([]),
    )
    monkeypatch.setattr(
        "aa_auto_sdr.sdr.builder.fetch.fetch_classification_datasets",
        lambda _c, _r: FetchOutcome.healthy([]),
    )


def test_default_quality_is_none(fake_client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fetchers(monkeypatch)
    doc = build_sdr(
        fake_client,
        "rs1",
        captured_at=datetime(2026, 5, 9, tzinfo=UTC),
        tool_version="1.9.0",
    )
    assert doc.quality is None


def test_audit_naming_stamps_naming_audit_block(fake_client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fetchers(monkeypatch)
    doc = build_sdr(
        fake_client,
        "rs1",
        captured_at=datetime(2026, 5, 9, tzinfo=UTC),
        tool_version="1.9.0",
        audit_naming=True,
    )
    assert doc.quality is not None
    assert "naming_audit" in doc.quality
    assert doc.quality["naming_audit"]["total_components"] == 2
    assert "stale_components" not in doc.quality


def test_flag_stale_stamps_stale_block(fake_client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fetchers(monkeypatch)
    doc = build_sdr(
        fake_client,
        "rs1",
        captured_at=datetime(2026, 5, 9, tzinfo=UTC),
        tool_version="1.9.0",
        flag_stale=True,
    )
    assert doc.quality is not None
    assert "stale_components" in doc.quality
    assert len(doc.quality["stale_components"]) == 1  # "old_thing"
    assert doc.quality["stale_components"][0]["name"] == "old_thing"
    assert "naming_audit" not in doc.quality


def test_both_flags_stamp_both_blocks(fake_client: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fetchers(monkeypatch)
    doc = build_sdr(
        fake_client,
        "rs1",
        captured_at=datetime(2026, 5, 9, tzinfo=UTC),
        tool_version="1.9.0",
        audit_naming=True,
        flag_stale=True,
    )
    assert doc.quality is not None
    assert "naming_audit" in doc.quality
    assert "stale_components" in doc.quality
