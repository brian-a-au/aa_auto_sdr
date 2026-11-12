"""Tests for the --notion-print-database-schema fast-path command."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest


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
    err = capsys.readouterr().err
    assert rc == 2
    assert "cannot be combined" in err


def _fast_path_output() -> str:
    from aa_auto_sdr.output.notion_database import schema_cheatsheet

    return schema_cheatsheet()


def test_print_schema_after_another_flag_prints_schema(capsys, tmp_path, monkeypatch):
    """The flag is registered in the parser, so it works in any argument
    position and prints exactly what the fast path prints."""
    from aa_auto_sdr.__main__ import main as entry

    monkeypatch.chdir(tmp_path)
    rc = entry(["--quiet", "--notion-print-database-schema"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == _fast_path_output()


def test_print_schema_before_another_flag_prints_schema(capsys, tmp_path, monkeypatch):
    from aa_auto_sdr.__main__ import main as entry

    monkeypatch.chdir(tmp_path)
    rc = entry(["--notion-print-database-schema", "--quiet"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out == _fast_path_output()


def test_print_schema_through_parser_makes_no_client_or_credential_call(capsys, tmp_path, monkeypatch):
    from aa_auto_sdr.__main__ import main as entry
    from aa_auto_sdr.api import client as client_mod
    from aa_auto_sdr.core import credentials

    def _boom(*_a, **_k):
        raise AssertionError("must not resolve credentials or build a client")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(credentials, "resolve", _boom)
    monkeypatch.setattr(client_mod.AaClient, "from_credentials", classmethod(_boom))
    rc = entry(["--log-level", "ERROR", "--notion-print-database-schema"])
    assert rc == 0
    assert capsys.readouterr().out == _fast_path_output()


def test_print_schema_with_positional_after_flag_exits_usage(capsys, tmp_path, monkeypatch):
    from aa_auto_sdr.__main__ import main as entry

    monkeypatch.chdir(tmp_path)
    rc = entry(["--quiet", "--notion-print-database-schema", "rs1"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "cannot be combined" in captured.err
    assert captured.out == ""


def test_print_schema_with_another_action_exits_usage(capsys):
    from aa_auto_sdr.__main__ import main as entry

    with pytest.raises(SystemExit) as exc:
        entry(["--quiet", "--notion-print-database-schema", "--list-reportsuites"])
    assert exc.value.code == 2


def test_print_schema_with_git_commit_exits_usage(capsys, tmp_path, monkeypatch):
    from aa_auto_sdr.__main__ import main as entry

    monkeypatch.chdir(tmp_path)
    rc = entry(["--git-commit", "--notion-print-database-schema"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "requires an SDR-generating action" in err


def test_print_schema_with_push_to_notion_exits_usage(capsys, tmp_path, monkeypatch):
    from aa_auto_sdr.__main__ import main as entry

    monkeypatch.chdir(tmp_path)
    rc = entry(["--push-to-notion", "sdr.json", "--notion-print-database-schema"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "--push-to-notion cannot be combined with --notion-print-database-schema" in err


def test_print_schema_with_notion_create_database_exits_usage(capsys, tmp_path, monkeypatch):
    from aa_auto_sdr.__main__ import main as entry

    monkeypatch.chdir(tmp_path)
    rc = entry(["--notion-create-database", "--notion-print-database-schema"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "--notion-create-database cannot be combined with --notion-print-database-schema" in err


def test_print_schema_is_in_help_text(capsys):
    from aa_auto_sdr.__main__ import _print_help

    _print_help()
    assert "--notion-print-database-schema" in capsys.readouterr().out


def test_print_schema_is_in_parser_and_completions(capsys):
    from aa_auto_sdr.cli.commands.completion import run_completion
    from aa_auto_sdr.cli.parser import build_parser

    options = {o for a in build_parser()._actions for o in a.option_strings}
    assert "--notion-print-database-schema" in options
    for shell, token in (("bash", "--notion-print-database-schema"), ("zsh", "--notion-print-database-schema")):
        assert run_completion(shell) == 0
        assert token in capsys.readouterr().out
    assert run_completion("fish") == 0
    assert "notion-print-database-schema" in capsys.readouterr().out
