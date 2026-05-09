"""v1.5 — assert build_sdr emits two DEBUG records (entry + exit)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.api.models import FetchOutcome
from aa_auto_sdr.sdr.builder import build_sdr


@pytest.fixture(autouse=True)
def _isolate_package_logger():
    """Pattern B per disambiguation table — build_sdr doesn't call setup_logging."""
    pkg = logging.getLogger("aa_auto_sdr")
    saved_handlers = pkg.handlers[:]
    saved_level = pkg.level
    pkg.handlers.clear()
    try:
        yield
    finally:
        pkg.handlers.clear()
        for h in saved_handlers:
            pkg.addHandler(h)
        pkg.setLevel(saved_level)


def test_build_sdr_emits_entry_and_exit_debug(caplog):
    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.sdr.builder")
    fake_client = MagicMock()

    with (
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_report_suite") as rs,
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_dimensions", return_value=[]),
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_metrics", return_value=[]),
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_segments", return_value=[]),
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_calculated_metrics", return_value=[]),
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_virtual_report_suites", return_value=[]),
        patch("aa_auto_sdr.sdr.builder.fetch.fetch_classification_datasets", return_value=FetchOutcome.healthy([])),
    ):
        rs.return_value = MagicMock(rsid="RS1", name="n", timezone=None, currency=None, parent_rsid=None)
        build_sdr(
            fake_client,
            "RS1",
            captured_at=datetime.now(UTC),
            tool_version="1.5.0",
        )

    debugs = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert len(debugs) >= 2
    entry_rec = debugs[0]
    assert entry_rec.rsid == "RS1"
    assert entry_rec.tool_version == "1.5.0"
    exit_rec = debugs[-1]
    assert exit_rec.rsid == "RS1"
    assert isinstance(exit_rec.count, int)
    assert isinstance(exit_rec.duration_ms, int)
