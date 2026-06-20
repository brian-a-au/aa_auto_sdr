"""Tests for the --notion-print-database-schema fast-path command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch


def test_run_notion_print_schema_prints_and_exits_ok(capsys):
    from aa_auto_sdr.cli.commands.notion_schema import run_notion_print_schema

    rc = run_notion_print_schema()

    out = capsys.readouterr().out
    assert rc == 0
    assert "RSID" in out
    assert "rich_text" in out
    assert "NOTION_REGISTRY_DATABASE_ID" in out


def test_fastpath_dispatch_in_main_skips_heavy_imports():
    """The fast-path handler must not import pandas / aanalytics2 / notion_client."""
    import sys

    # Snapshot what's already imported (test session may have loaded them already).
    initial = set(sys.modules)

    from aa_auto_sdr.__main__ import main as entry

    with patch("sys.stdout", new=StringIO()):
        rc = entry(["--notion-print-database-schema"])

    assert rc == 0

    newly_imported = set(sys.modules) - initial
    forbidden = {"pandas", "aanalytics2", "notion_client", "xlsxwriter"}
    leaked = newly_imported & forbidden
    assert not leaked, f"Fast-path leaked heavy imports: {leaked}"


def test_print_schema_combined_with_args_exits_usage(capsys):
    """Print-and-exit must be used alone; combining it with work is USAGE."""
    from aa_auto_sdr.__main__ import main as entry

    rc = entry(["--notion-print-database-schema", "examplersid1"])
    out = capsys.readouterr().out
    assert rc == 2
    assert "cannot be combined" in out
