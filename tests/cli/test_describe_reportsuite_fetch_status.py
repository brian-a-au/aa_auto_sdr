"""--describe-reportsuite consumes FetchOutcome status — see spec §4.2."""

from __future__ import annotations

import json as _json
from io import StringIO
from unittest.mock import MagicMock, patch

from aa_auto_sdr.api import models
from aa_auto_sdr.cli.commands.inspect import run_describe_reportsuite


def _stub_rs() -> models.ReportSuite:
    return models.ReportSuite(
        rsid="demo.prod",
        name="Demo Production",
        timezone="UTC",
        currency="USD",
        parent_rsid=None,
    )


def _stubs(*, vrs_outcome, cls_outcome, dimensions=None, metrics=None):
    """Patch every fetcher run_describe_reportsuite calls."""
    return [
        patch("aa_auto_sdr.cli.commands.inspect._bootstrap", return_value=(MagicMock(), 0)),
        patch(
            "aa_auto_sdr.cli.commands.inspect.fetch.resolve_rsid",
            return_value=(["demo.prod"], False),
        ),
        patch(
            "aa_auto_sdr.cli.commands.inspect.fetch.fetch_report_suite",
            return_value=_stub_rs(),
        ),
        patch(
            "aa_auto_sdr.cli.commands.inspect.fetch.fetch_dimensions",
            return_value=dimensions or [],
        ),
        patch(
            "aa_auto_sdr.cli.commands.inspect.fetch.fetch_metrics",
            return_value=metrics or [],
        ),
        patch("aa_auto_sdr.cli.commands.inspect.fetch.fetch_segments", return_value=[]),
        patch(
            "aa_auto_sdr.cli.commands.inspect.fetch.fetch_calculated_metrics",
            return_value=[],
        ),
        patch(
            "aa_auto_sdr.cli.commands.inspect.fetch.fetch_virtual_report_suites",
            return_value=vrs_outcome,
        ),
        patch(
            "aa_auto_sdr.cli.commands.inspect.fetch.fetch_classification_datasets",
            return_value=cls_outcome,
        ),
    ]


def _run_describe(format_name: str | None) -> str:
    """Invoke run_describe_reportsuite and capture stdout."""
    buf = StringIO()
    with patch("sys.stdout", buf):
        run_describe_reportsuite(
            identifier="demo.prod",
            profile=None,
            format_name=format_name,
            output=None,
        )
    return buf.getvalue()


def test_healthy_run_no_asterisks_no_footer() -> None:
    """All-healthy run renders byte-identical to v1.7.1 output (no asterisks, no footer)."""
    patches = _stubs(
        vrs_outcome=models.FetchOutcome.healthy([]),
        cls_outcome=models.FetchOutcome.healthy([]),
    )
    for p in patches:
        p.start()
    try:
        out = _run_describe(format_name=None)
    finally:
        for p in patches:
            p.stop()
    assert "*" not in out
    assert "fetch degraded" not in out
    assert "demo.prod" in out


def test_degraded_vrs_renders_asterisk_and_footer() -> None:
    """Degraded VRS → cell shows count with asterisk, footer line + disclaimer."""
    patches = _stubs(
        vrs_outcome=models.FetchOutcome.degraded(),
        cls_outcome=models.FetchOutcome.healthy([]),
    )
    for p in patches:
        p.start()
    try:
        out = _run_describe(format_name=None)
    finally:
        for p in patches:
            p.stop()
    # Cell asterisk: "0 *" appears as a column value
    assert " 0 *" in out or "0 *" in out
    # Footer line
    assert "* demo.prod virtual_report_suites: fetch degraded" in out
    assert "* (counts marked with * may be inaccurate; see logs/SDR_*.log)" in out


def test_degraded_both_renders_two_footer_lines() -> None:
    patches = _stubs(
        vrs_outcome=models.FetchOutcome.degraded(),
        cls_outcome=models.FetchOutcome.degraded(),
    )
    for p in patches:
        p.start()
    try:
        out = _run_describe(format_name=None)
    finally:
        for p in patches:
            p.stop()
    assert "* demo.prod classifications: fetch degraded" in out
    assert "* demo.prod virtual_report_suites: fetch degraded" in out
    assert "* (counts marked with *" in out


def test_json_output_emits_fetch_status_field() -> None:
    patches = _stubs(
        vrs_outcome=models.FetchOutcome.degraded(),
        cls_outcome=models.FetchOutcome.healthy([]),
    )
    for p in patches:
        p.start()
    try:
        out = _run_describe(format_name="json")
    finally:
        for p in patches:
            p.stop()
    data = _json.loads(out)
    assert isinstance(data, list)
    rec = data[0]
    assert rec["rsid"] == "demo.prod"
    assert rec["virtual_report_suites"] == 0
    assert rec["fetch_status"] == {
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
        out = _run_describe(format_name="json")
    finally:
        for p in patches:
            p.stop()
    data = _json.loads(out)
    rec = data[0]
    assert "fetch_status" not in rec


def test_json_output_partial_carries_expansion_level() -> None:
    patches = _stubs(
        vrs_outcome=models.FetchOutcome.partial([], expansion_level="minimal"),
        cls_outcome=models.FetchOutcome.healthy([]),
    )
    for p in patches:
        p.start()
    try:
        out = _run_describe(format_name="json")
    finally:
        for p in patches:
            p.stop()
    data = _json.loads(out)
    assert data[0]["fetch_status"]["virtual_report_suites"] == {
        "status": "partial",
        "expansion_level": "minimal",
    }


def test_describe_calls_fetchers_with_count_only_true() -> None:
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
    # Replace the VRS / classifications stubs with kwarg-capturing wrappers.
    base_patches[-2] = patch(
        "aa_auto_sdr.cli.commands.inspect.fetch.fetch_virtual_report_suites",
        side_effect=mock_vrs,
    )
    base_patches[-1] = patch(
        "aa_auto_sdr.cli.commands.inspect.fetch.fetch_classification_datasets",
        side_effect=mock_cls,
    )
    for p in base_patches:
        p.start()
    try:
        _run_describe(format_name="json")
    finally:
        for p in base_patches:
            p.stop()
    assert vrs_call_kwargs == {"count_only": True}
    assert cls_call_kwargs == {"count_only": True}
