"""build_footer + annotate_cells helpers — see spec §4.5.

These functions are part of cli/list_output.py's public API: they're consumed
across modules by both inspect.py (describe) and stats.py.
"""

from __future__ import annotations

from aa_auto_sdr.cli.list_output import annotate_cells, build_footer


def testbuild_footer_empty_records_returns_empty() -> None:
    assert build_footer([]) == []


def testbuild_footer_all_healthy_records_returns_empty() -> None:
    records = [
        {"rsid": "r1", "virtual_report_suites": 5, "classifications": 3},
        {"rsid": "r2", "virtual_report_suites": 0},
    ]
    assert build_footer(records) == []


def testbuild_footer_degraded_vrs_one_record() -> None:
    records = [
        {
            "rsid": "demo.prod",
            "virtual_report_suites": 0,
            "fetch_status": {
                "virtual_report_suites": {"status": "degraded", "expansion_level": None},
            },
        },
    ]
    out = build_footer(records)
    assert out == [
        "* demo.prod virtual_report_suites: fetch degraded",
        "* (counts marked with * may be inaccurate; see logs/SDR_*.log)",
    ]


def testbuild_footer_partial_carries_expansion_level() -> None:
    records = [
        {
            "rsid": "demo.prod",
            "virtual_report_suites": 5,
            "fetch_status": {
                "virtual_report_suites": {"status": "partial", "expansion_level": "minimal"},
            },
        },
    ]
    out = build_footer(records)
    assert "fetch partial (expansion_level=minimal)" in out[0]


def testbuild_footer_multiple_components_sorted() -> None:
    """Multiple components on one record sort alphabetically by component_type."""
    records = [
        {
            "rsid": "demo.prod",
            "fetch_status": {
                "virtual_report_suites": {"status": "degraded", "expansion_level": None},
                "classifications": {"status": "degraded", "expansion_level": None},
            },
        },
    ]
    out = build_footer(records)
    # Alphabetical: classifications before virtual_report_suites
    assert "classifications" in out[0]
    assert "virtual_report_suites" in out[1]
    assert out[2] == "* (counts marked with * may be inaccurate; see logs/SDR_*.log)"


def testbuild_footer_omits_rsid_when_record_lacks_one() -> None:
    """Records without rsid (e.g., describe with single output) get a bare prefix."""
    records = [
        {
            "fetch_status": {
                "classifications": {"status": "degraded", "expansion_level": None},
            },
        },
    ]
    out = build_footer(records)
    assert out[0] == "* classifications: fetch degraded"


def testbuild_footer_multi_record_order_follows_input() -> None:
    """Footer lines for multiple records preserve input order (no rsid sort)."""
    records = [
        {
            "rsid": "z.suite",
            "fetch_status": {
                "virtual_report_suites": {"status": "degraded", "expansion_level": None},
            },
        },
        {
            "rsid": "a.suite",
            "fetch_status": {
                "virtual_report_suites": {"status": "degraded", "expansion_level": None},
            },
        },
    ]
    out = build_footer(records)
    assert out[0].startswith("* z.suite")
    assert out[1].startswith("* a.suite")


def testannotate_cells_no_fetch_status_returns_unchanged() -> None:
    records = [{"rsid": "r1", "virtual_report_suites": 5}]
    out = annotate_cells(records)
    assert out == records
    # Ensure no mutation
    assert out is not records
    assert out[0] is not records[0]


def testannotate_cells_appends_asterisk() -> None:
    records = [
        {
            "rsid": "r1",
            "virtual_report_suites": 0,
            "classifications": 5,
            "fetch_status": {
                "virtual_report_suites": {"status": "degraded", "expansion_level": None},
            },
        },
    ]
    out = annotate_cells(records)
    assert out[0]["virtual_report_suites"] == "0 *"
    assert out[0]["classifications"] == 5  # unchanged


def testannotate_cells_does_not_mutate_originals() -> None:
    records = [
        {
            "rsid": "r1",
            "virtual_report_suites": 0,
            "fetch_status": {
                "virtual_report_suites": {"status": "degraded", "expansion_level": None},
            },
        },
    ]
    out = annotate_cells(records)
    # Originals preserved
    assert records[0]["virtual_report_suites"] == 0
    # Annotated copies separate
    assert out[0]["virtual_report_suites"] == "0 *"
    assert out[0] is not records[0]
