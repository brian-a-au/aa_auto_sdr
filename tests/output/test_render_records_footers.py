"""render_records footers parameter — see spec §4.5."""

from __future__ import annotations

import json as _json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from aa_auto_sdr.cli.list_output import render_records


def _capture_stdout(fn) -> str:
    buf = StringIO()
    with patch("sys.stdout", buf):
        fn()
    return buf.getvalue()


def _records() -> list[dict]:
    return [{"id": "r1", "name": "First"}, {"id": "r2", "name": "Second"}]


def test_implicit_table_prints_footers_after_table() -> None:
    out = _capture_stdout(
        lambda: render_records(
            _records(),
            format_name=None,
            output=None,
            columns=["id", "name"],
            footers=["* footer line 1", "* (disclaimer)"],
        ),
    )
    # Records appear before footer
    assert "r1" in out
    idx_record = out.index("r1")
    idx_footer = out.index("* footer line 1")
    assert idx_record < idx_footer
    assert "* (disclaimer)" in out


def test_implicit_table_no_footers_when_none() -> None:
    out = _capture_stdout(
        lambda: render_records(
            _records(),
            format_name=None,
            output=None,
            columns=["id", "name"],
            footers=None,
        ),
    )
    assert "* " not in out


def test_implicit_table_no_footers_when_empty_list() -> None:
    out = _capture_stdout(
        lambda: render_records(
            _records(),
            format_name=None,
            output=None,
            columns=["id", "name"],
            footers=[],
        ),
    )
    assert "* " not in out


def test_json_format_ignores_footers() -> None:
    """footers leak into JSON output → bug. Verify isolation."""
    out = _capture_stdout(
        lambda: render_records(
            _records(),
            format_name="json",
            output=None,
            columns=["id", "name"],
            footers=["* footer line"],
        ),
    )
    assert "* footer line" not in out
    # JSON output is valid (no stray text appended)
    parsed = _json.loads(out)
    assert isinstance(parsed, list)
    assert len(parsed) == 2


def test_csv_format_ignores_footers(tmp_path: Path) -> None:
    """footers leak into CSV output → bug. Verify isolation (CSV writes to file)."""
    target = tmp_path / "out.csv"
    render_records(
        _records(),
        format_name="csv",
        output=target,
        columns=["id", "name"],
        footers=["* footer line"],
    )
    csv_text = target.read_text(encoding="utf-8-sig")
    assert "* footer line" not in csv_text


def test_default_footers_is_none() -> None:
    """Existing callers that don't pass footers continue to work byte-identically."""
    out = _capture_stdout(
        lambda: render_records(
            _records(),
            format_name=None,
            output=None,
            columns=["id", "name"],
        ),
    )
    assert "* " not in out
    assert "r1" in out
