"""Format-list swap helper — replaces 'excel' with 'excel-template'. v1.16.0."""

from __future__ import annotations

from aa_auto_sdr.output.registry import swap_excel_for_template


def test_swap_single_excel() -> None:
    assert swap_excel_for_template(["excel"]) == ["excel-template"]


def test_swap_in_multi_format_preserves_order() -> None:
    assert swap_excel_for_template(["excel", "csv", "json"]) == [
        "excel-template",
        "csv",
        "json",
    ]


def test_swap_no_excel_unchanged() -> None:
    assert swap_excel_for_template(["csv", "json", "markdown"]) == [
        "csv",
        "json",
        "markdown",
    ]


def test_swap_dedups_when_both_excel_and_excel_template_present() -> None:
    """If a future alias somehow includes both, the result is deduped — first wins."""
    assert swap_excel_for_template(["excel", "excel-template", "csv"]) == [
        "excel-template",
        "csv",
    ]


def test_swap_preserves_full_alias_set() -> None:
    """`all` alias-equivalent list: every format present."""
    formats = ["excel", "csv", "json", "html", "markdown"]
    assert swap_excel_for_template(formats) == [
        "excel-template",
        "csv",
        "json",
        "html",
        "markdown",
    ]
