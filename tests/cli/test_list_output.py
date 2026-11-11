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


_HOSTILE = [
    {"id": "a", "name": '=HYPERLINK("x")'},
    {"id": "b", "name": "+1"},
    {"id": "c", "name": "@x"},
    {"id": "d", "name": "-y"},
    {"id": "e", "name": "plain"},
]
_EXPECTED = ['\'=HYPERLINK("x")', "'+1", "'@x", "'-y", "plain"]


def test_csv_file_neutralizes_formula_cells(tmp_path: Path) -> None:
    target = tmp_path / "out.csv"
    assert render_records(_HOSTILE, format_name="csv", output=target, columns=None) == 0
    rows = list(_csv.reader(io.StringIO(target.read_text(encoding="utf-8-sig"))))
    assert rows[0] == ["id", "name"]
    assert [r[1] for r in rows[1:]] == _EXPECTED


def test_csv_stdout_neutralizes_formula_cells(capsys) -> None:
    assert render_records(_HOSTILE, format_name="csv", output=Path("-"), columns=None) == 0
    rows = list(_csv.reader(io.StringIO(capsys.readouterr().out)))
    assert [r[1] for r in rows[1:]] == _EXPECTED


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


def test_atomic_write_cleans_up_temp_on_failure(tmp_path: Path, monkeypatch, capsys) -> None:
    """If os.replace fails mid-write, the temp file is removed and the run exits 15."""
    import aa_auto_sdr.cli.list_output as lo

    target = tmp_path / "out.json"

    def _boom(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(lo.os, "replace", _boom)
    assert render_records(_RECORDS, format_name="json", output=target, columns=None) == 15
    assert "disk full" in capsys.readouterr().err
    # No target written and no orphaned temp file left behind.
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("fmt", ["json", "csv"])
def test_file_write_failure_returns_output_exit(tmp_path: Path, capsys, fmt) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    target = blocker / f"out.{fmt}"
    rc = render_records([{"id": "a"}], format_name=fmt, output=target, columns=None)
    captured = capsys.readouterr()
    assert rc == 15
    assert f"error: could not write {target}" in captured.err
    assert captured.out == ""


# --- CSV on a Windows-style stdout -------------------------------------------
# csv.writer already ends each row with "\r\n". A Windows text stdout turns
# every "\n" into "\r\n" again, so writing the CSV text through it gives
# "\r\r\n" and a blank line between rows. These tests use a TextIOWrapper with
# newline="\r\n" to emulate that stream on any platform.

_STDOUT_RECORDS = [
    {"rsid": "rs-a", "name": "Shop"},
    {"rsid": "rs-b", "name": "shop"},
]


def _windows_stdout(**kwargs) -> tuple[io.BytesIO, io.TextIOWrapper]:
    raw = io.BytesIO()
    kwargs.setdefault("encoding", "utf-8")
    return raw, io.TextIOWrapper(raw, newline="\r\n", **kwargs)


def test_csv_stdout_has_single_cr_on_windows_text_stream(monkeypatch) -> None:
    raw, stream = _windows_stdout()
    monkeypatch.setattr("sys.stdout", stream)
    assert render_records(_STDOUT_RECORDS, format_name="csv", output=Path("-"), columns=None) == 0
    stream.flush()
    assert raw.getvalue() == b"rsid,name\r\nrs-a,Shop\r\nrs-b,shop\r\n"


def test_csv_stdout_non_ascii_uses_stream_error_handler(monkeypatch) -> None:
    raw, stream = _windows_stdout(encoding="cp1252", errors="backslashreplace")
    monkeypatch.setattr("sys.stdout", stream)
    records = [{"rsid": "rs-a", "name": "日本"}]
    assert render_records(records, format_name="csv", output=Path("-"), columns=None) == 0
    stream.flush()
    data = raw.getvalue()
    assert b"\\u65e5" in data
    assert b"\r\r\n" not in data


def test_csv_stdout_non_ascii_uses_softened_stdout_handler(monkeypatch) -> None:
    """The error handler __main__ installs on a non-UTF-8 stdout must still apply."""
    from aa_auto_sdr.__main__ import _soften_stdout_errors

    raw, stream = _windows_stdout(encoding="cp1252")
    monkeypatch.setattr("sys.stdout", stream)
    _soften_stdout_errors()
    assert stream.errors == "aa_auto_sdr.json_escape"
    records = [{"rsid": "rs-a", "name": "Café 日本"}]
    assert render_records(records, format_name="csv", output=Path("-"), columns=None) == 0
    stream.flush()
    assert raw.getvalue() == b"rsid,name\r\nrs-a,Caf\xe9 \\u65e5\\u672c\r\n"


def test_csv_stdout_falls_back_without_buffer(monkeypatch) -> None:
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    assert render_records(_STDOUT_RECORDS, format_name="csv", output=Path("-"), columns=None) == 0
    assert out.getvalue() == "rsid,name\r\nrs-a,Shop\r\nrs-b,shop\r\n"
