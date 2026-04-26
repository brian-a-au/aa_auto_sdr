"""Render a list of records to stdout, file, or stdout-pipe.

Three format paths:
  - implicit table (format_name=None) — fixed-width to stdout only
  - json — array of objects
  - csv — RFC4180 with UTF-8-BOM for files, no BOM for stdout

Honors output=None (stdout default), output=Path("-") (explicit stdout pipe),
output=Path(other) (file). Implicit table format rejects file output."""

from __future__ import annotations

import csv as _csv
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from aa_auto_sdr.output._helpers import stringify_cell

_EXIT_OK = 0
_EXIT_OUTPUT = 15


def render_records(
    records: list[dict[str, Any]],
    *,
    format_name: str | None,
    output: Path | None,
    columns: list[str] | None,
) -> int:
    cols = columns if columns is not None else _derive_columns(records)

    is_pipe = output == Path("-")
    is_file = output is not None and not is_pipe

    if format_name is None:
        # Implicit table — stdout only
        if is_file:
            print(
                "error: implicit table format cannot be written to a file; use --format json or csv",
                file=sys.stderr,
                flush=True,
            )
            return _EXIT_OUTPUT
        _print_table(records, cols)
        if not records:
            print("# 0 records", file=sys.stderr, flush=True)
        return _EXIT_OK

    if format_name == "json":
        body = json.dumps([_project(r, cols) for r in records], indent=2, default=str)
        if is_file:
            target = output if output.suffix == ".json" else output.with_suffix(".json")
            _atomic_write_text(target, body + "\n", encoding="utf-8")
        else:
            print(body, flush=True)
        if not records:
            print("# 0 records", file=sys.stderr, flush=True)
        return _EXIT_OK

    if format_name == "csv":
        body = _format_csv(records, cols)
        if is_file:
            target = output if output.suffix == ".csv" else output.with_suffix(".csv")
            _atomic_write_text(target, body, encoding="utf-8-sig")
        else:
            # No BOM for stdout; write the body as-is
            sys.stdout.write(body)
            sys.stdout.flush()
        if not records:
            print("# 0 records", file=sys.stderr, flush=True)
        return _EXIT_OK

    print(f"error: unknown format {format_name!r}", file=sys.stderr, flush=True)
    return _EXIT_OUTPUT


def _derive_columns(records: list[dict[str, Any]]) -> list[str]:
    if not records:
        return []
    return list(records[0].keys())


def _project(record: dict[str, Any], cols: list[str]) -> dict[str, Any]:
    return {c: record.get(c) for c in cols}


def _format_csv(records: list[dict[str, Any]], cols: list[str]) -> str:
    buf = io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(cols)
    for r in records:
        writer.writerow([stringify_cell(r.get(c)) for c in cols])
    return buf.getvalue()


def _print_table(records: list[dict[str, Any]], cols: list[str]) -> None:
    """Print a fixed-width table to stdout. Columns sized to widest cell."""
    if not cols:
        return
    str_rows = [{c: stringify_cell(r.get(c)) for c in cols} for r in records]
    widths = {c: max(len(c), max((len(row[c]) for row in str_rows), default=0)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    sep = "  ".join("-" * widths[c] for c in cols)
    print(header)
    print(sep)
    for row in str_rows:
        print("  ".join(row[c].ljust(widths[c]) for c in cols))


def _atomic_write_text(path: Path, content: str, *, encoding: str) -> None:
    """Atomic file write via tempfile + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
