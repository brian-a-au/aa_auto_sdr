"""list_output.render_records — fixed-width table / json / csv to stdout/file."""

import csv as _csv
import io
import json
from pathlib import Path

import pytest

from aa_auto_sdr.cli.list_output import render_records

_RECORDS = [
    {"id": "evar1", "name": "User ID", "type": "string"},
    {"id": "evar2", "name": "Plan", "type": "string"},
]


def test_default_format_prints_fixed_width_table_to_stdout(capsys) -> None:
    rc = render_records(_RECORDS, format_name=None, output=None, columns=None)
    assert rc == 0
    out = capsys.readouterr().out
    # Header line and at least one data line
    assert "id" in out
    assert "name" in out
    assert "type" in out
    assert "evar1" in out
    assert "User ID" in out


def test_json_format_to_stdout(capsys) -> None:
    rc = render_records(_RECORDS, format_name="json", output=None, columns=None)
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed == _RECORDS


def test_json_format_to_file(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    rc = render_records(_RECORDS, format_name="json", output=target, columns=None)
    assert rc == 0
    parsed = json.loads(target.read_text())
    assert parsed == _RECORDS


def test_json_format_explicit_stdout_pipe(capsys) -> None:
    rc = render_records(_RECORDS, format_name="json", output=Path("-"), columns=None)
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed == _RECORDS


def test_csv_format_to_stdout(capsys) -> None:
    rc = render_records(_RECORDS, format_name="csv", output=None, columns=None)
    assert rc == 0
    out = capsys.readouterr().out
    rows = list(_csv.reader(io.StringIO(out)))
    assert rows[0] == ["id", "name", "type"]
    assert rows[1] == ["evar1", "User ID", "string"]


def test_csv_format_to_file_has_bom(tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    rc = render_records(_RECORDS, format_name="csv", output=target, columns=None)
    assert rc == 0
    raw = target.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM


def test_csv_format_explicit_stdout_no_bom(capsys) -> None:
    rc = render_records(_RECORDS, format_name="csv", output=Path("-"), columns=None)
    assert rc == 0
    out = capsys.readouterr().out
    # No BOM in stdout — pipes don't need it
    assert not out.startswith("﻿")


def test_implicit_table_to_file_rejects(tmp_path: Path, capsys) -> None:
    target = tmp_path / "out.txt"
    rc = render_records(_RECORDS, format_name=None, output=target, columns=None)
    assert rc == 15
    err = capsys.readouterr().err
    assert "implicit table" in err or "table format" in err
    assert not target.exists()


def test_empty_records_prints_header_and_stderr_note(capsys) -> None:
    rc = render_records([], format_name=None, output=None, columns=["id", "name"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "id" in captured.out
    assert "name" in captured.out
    assert "0 records" in captured.err


def test_empty_records_json_returns_empty_array(capsys) -> None:
    rc = render_records([], format_name="json", output=None, columns=None)
    assert rc == 0
    out = capsys.readouterr().out
    assert json.loads(out) == []


def test_explicit_columns_override_record_keys(capsys) -> None:
    """When columns is given, only those columns are emitted (in order)."""
    rc = render_records(_RECORDS, format_name="csv", output=None, columns=["name", "id"])
    assert rc == 0
    out = capsys.readouterr().out
    rows = list(_csv.reader(io.StringIO(out)))
    assert rows[0] == ["name", "id"]
    assert rows[1] == ["User ID", "evar1"]


def test_nested_dict_in_value_serializes_via_stringify_cell(capsys) -> None:
    """Nested dict cells should serialize to compact JSON, not Python repr."""
    records = [{"id": "s_1", "definition": {"hits": "mobile"}}]
    rc = render_records(records, format_name="csv", output=None, columns=None)
    assert rc == 0
    out = capsys.readouterr().out
    rows = list(_csv.reader(io.StringIO(out)))
    assert rows[1][1] == '{"hits": "mobile"}'


def test_json_output_appends_extension_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "out"  # no .json suffix
    rc = render_records(_RECORDS, format_name="json", output=target, columns=None)
    assert rc == 0
    assert (tmp_path / "out.json").exists()


def test_csv_output_appends_extension_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "out"
    rc = render_records(_RECORDS, format_name="csv", output=target, columns=None)
    assert rc == 0
    assert (tmp_path / "out.csv").exists()


def test_build_footer_skips_healthy_status_entries() -> None:
    """A healthy fetch_status entry is defensively skipped — no footer line."""
    from aa_auto_sdr.cli.list_output import build_footer

    records = [
        {
            "rsid": "rs1",
            "fetch_status": {"virtual_report_suites": {"status": "healthy", "expansion_level": "full"}},
        },
    ]
    assert build_footer(records) == []


def test_csv_empty_records_prints_stderr_note(capsys) -> None:
    rc = render_records([], format_name="csv", output=None, columns=["id", "name"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "0 records" in captured.err


def test_unknown_format_returns_output_exit(capsys) -> None:
    rc = render_records(_RECORDS, format_name="xml", output=None, columns=None)
    assert rc == 15
    assert "unknown format" in capsys.readouterr().err


def test_implicit_table_empty_records_no_columns_prints_note(capsys) -> None:
    """Empty records with no explicit columns yields empty cols — table is a no-op."""
    rc = render_records([], format_name=None, output=None, columns=None)
    assert rc == 0
    captured = capsys.readouterr()
    assert "0 records" in captured.err


def test_atomic_write_cleans_up_temp_on_failure(tmp_path: Path, monkeypatch) -> None:
    """If os.replace fails mid-write, the temp file is removed and the error propagates."""
    import aa_auto_sdr.cli.list_output as lo

    target = tmp_path / "out.json"

    def _boom(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(lo.os, "replace", _boom)
    with pytest.raises(OSError, match="disk full"):
        render_records(_RECORDS, format_name="json", output=target, columns=None)
    # No target written and no orphaned temp file left behind.
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []
