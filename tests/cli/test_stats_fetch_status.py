"""--stats consumes FetchOutcome status — see spec §4.3."""

from __future__ import annotations

import json as _json
from io import StringIO
from unittest.mock import MagicMock, patch

from aa_auto_sdr.api import models
from aa_auto_sdr.cli.commands.stats import run as run_stats


def _stub_rs(rsid: str = "demo.prod", name: str = "Demo Production") -> models.ReportSuite:
    return models.ReportSuite(
        rsid=rsid,
        name=name,
        timezone="UTC",
        currency="USD",
        parent_rsid=None,
    )


def _stubs(*, vrs_outcome, cls_outcome, rsid: str = "demo.prod"):
    return [
        patch(
            "aa_auto_sdr.cli.commands.stats.credentials.resolve",
            return_value=MagicMock(),
        ),
        patch(
            "aa_auto_sdr.cli.commands.stats.AaClient.from_credentials",
            return_value=MagicMock(),
        ),
        patch(
            "aa_auto_sdr.cli.commands.stats.fetch.resolve_rsid",
            return_value=([rsid], False),
        ),
        patch(
            "aa_auto_sdr.cli.commands.stats.fetch.fetch_report_suite",
            return_value=_stub_rs(rsid=rsid),
        ),
        patch("aa_auto_sdr.cli.commands.stats.fetch.fetch_dimensions", return_value=[]),
        patch("aa_auto_sdr.cli.commands.stats.fetch.fetch_metrics", return_value=[]),
        patch("aa_auto_sdr.cli.commands.stats.fetch.fetch_segments", return_value=[]),
        patch(
            "aa_auto_sdr.cli.commands.stats.fetch.fetch_calculated_metrics",
            return_value=[],
        ),
        patch(
            "aa_auto_sdr.cli.commands.stats.fetch.fetch_virtual_report_suites",
            return_value=vrs_outcome,
        ),
        patch(
            "aa_auto_sdr.cli.commands.stats.fetch.fetch_classification_datasets",
            return_value=cls_outcome,
        ),
    ]


def _run_stats(format_name: str | None = None, rsid: str = "demo.prod") -> str:
    buf = StringIO()
    with patch("sys.stdout", buf):
        run_stats(rsids=[rsid], profile=None, format_name=format_name)
    return buf.getvalue()


def test_healthy_run_no_asterisks_no_footer() -> None:
    patches = _stubs(
        vrs_outcome=models.FetchOutcome.healthy([]),
        cls_outcome=models.FetchOutcome.healthy([]),
    )
    for p in patches:
        p.start()
    try:
        out = _run_stats(format_name="table")
    finally:
        for p in patches:
            p.stop()
    assert "*" not in out
    assert "fetch degraded" not in out
    assert "demo.prod" in out


def test_degraded_vrs_renders_asterisk_and_footer() -> None:
    patches = _stubs(
        vrs_outcome=models.FetchOutcome.degraded(),
        cls_outcome=models.FetchOutcome.healthy([]),
    )
    for p in patches:
        p.start()
    try:
        out = _run_stats(format_name="table")
    finally:
        for p in patches:
            p.stop()
    # Cell asterisk + footer
    assert "0 *" in out
    assert "* demo.prod virtual_report_suites: fetch degraded" in out
    assert "* (counts marked with * may be inaccurate; see logs/SDR_*.log)" in out


def test_json_output_emits_fetch_status_field() -> None:
    patches = _stubs(
        vrs_outcome=models.FetchOutcome.degraded(),
        cls_outcome=models.FetchOutcome.healthy([]),
    )
    for p in patches:
        p.start()
    try:
        out = _run_stats(format_name="json")
    finally:
        for p in patches:
            p.stop()
    data = _json.loads(out)
    assert isinstance(data, list)
    row = data[0]
    assert row["rsid"] == "demo.prod"
    assert row["counts"]["virtual_report_suites"] == 0
    assert row["fetch_status"] == {
        "virtual_report_suites": {"status": "degraded", "expansion_level": None},
    }


def test_json_output_omits_fetch_status_when_all_healthy() -> None:
    patches = _stubs(
        vrs_outcome=models.FetchOutcome.healthy([]),
        cls_outcome=models.FetchOutcome.healthy([]),
    )
    for p in patches:
        p.start()
    try:
        out = _run_stats(format_name="json")
    finally:
        for p in patches:
            p.stop()
    data = _json.loads(out)
    assert "fetch_status" not in data[0]


def test_stats_calls_fetchers_with_count_only_true() -> None:
    """Performance Item E: VRS + classifications fetched with count_only=True."""
    vrs_call_kwargs: dict = {}
    cls_call_kwargs: dict = {}

    def mock_vrs(*args, **kwargs):
        vrs_call_kwargs.update(kwargs)
        return models.FetchOutcome.healthy([])

    def mock_cls(*args, **kwargs):
        cls_call_kwargs.update(kwargs)
        return models.FetchOutcome.healthy([])

    base_patches = _stubs(
        vrs_outcome=models.FetchOutcome.healthy([]),
        cls_outcome=models.FetchOutcome.healthy([]),
    )
    base_patches[-2] = patch(
        "aa_auto_sdr.cli.commands.stats.fetch.fetch_virtual_report_suites",
        side_effect=mock_vrs,
    )
    base_patches[-1] = patch(
        "aa_auto_sdr.cli.commands.stats.fetch.fetch_classification_datasets",
        side_effect=mock_cls,
    )
    for p in base_patches:
        p.start()
    try:
        _run_stats(format_name="json")
    finally:
        for p in base_patches:
            p.stop()
    assert vrs_call_kwargs == {"count_only": True}
    assert cls_call_kwargs == {"count_only": True}


def test_json_output_partial_carries_expansion_level() -> None:
    """Partial VRS outcome surfaces expansion_level in fetch_status (parity w/ describe)."""
    patches = _stubs(
        vrs_outcome=models.FetchOutcome.partial([], expansion_level="minimal"),
        cls_outcome=models.FetchOutcome.healthy([]),
    )
    for p in patches:
        p.start()
    try:
        out = _run_stats(format_name="json")
    finally:
        for p in patches:
            p.stop()
    data = _json.loads(out)
    assert data[0]["fetch_status"]["virtual_report_suites"] == {
        "status": "partial",
        "expansion_level": "minimal",
    }


def test_table_both_degraded_renders_two_asterisks_and_two_footer_lines() -> None:
    """Both VRS and CLS degraded: both cells annotated, both footer lines present."""
    patches = _stubs(
        vrs_outcome=models.FetchOutcome.degraded(),
        cls_outcome=models.FetchOutcome.degraded(),
    )
    for p in patches:
        p.start()
    try:
        out = _run_stats(format_name="table")
    finally:
        for p in patches:
            p.stop()
    # Both count cells annotated
    assert out.count("0 *") >= 2
    # Both footer lines (alphabetical: classifications before virtual_report_suites)
    assert "* demo.prod classifications: fetch degraded" in out
    assert "* demo.prod virtual_report_suites: fetch degraded" in out
    assert "* (counts marked with * may be inaccurate; see logs/SDR_*.log)" in out
