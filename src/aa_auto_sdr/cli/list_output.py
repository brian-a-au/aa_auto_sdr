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

from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.output._helpers import stringify_cell


def build_footer(records: list[dict[str, Any]]) -> list[str]:
    """Build per-record-per-component footer lines + a generic disclaimer.

    Reads each record's `fetch_status` field (a dict mapping plural component
    type names like "virtual_report_suites" / "classifications" to a dict
    `{status, expansion_level}`). Returns lines like
    `* <rsid> virtual_report_suites: fetch degraded` plus a closing disclaimer
    when at least one record has a non-healthy entry. Returns [] otherwise.

    Component types within a record are sorted alphabetically; the rsid prefix
    is omitted when the record has no `rsid` key. See spec §4.5.
    """
    lines: list[str] = []
    for r in records:
        fs = r.get("fetch_status") or {}
        for ct, meta in sorted(fs.items()):
            status = meta.get("status")
            if status == "degraded":
                reason = "fetch degraded"
            elif status == "partial":
                reason = f"fetch partial (expansion_level={meta.get('expansion_level')})"
            else:
                continue  # healthy (defensive — builder should have filtered)
            rsid = r.get("rsid", "")
            prefix = f"* {rsid} {ct}" if rsid else f"* {ct}"
            lines.append(f"{prefix}: {reason}")
    if lines:
        lines.append("* (counts marked with * may be inaccurate; see logs/SDR_*.log)")
    return lines


def annotate_cells(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """For implicit-table rendering: rewrite annotated count cells to '<n> *'.

    Reads each record's `fetch_status` field; for each component_type listed,
    appends ' *' to that component's cell value (assumed to be a count).
    Returns a new list of dicts; original records are NOT mutated. Records
    without `fetch_status` pass through unchanged.

    The string-typed cell renders correctly under stats / list_output's
    fixed-width formatting via Python's :>N right-align spec. See spec §4.5.
    """
    out: list[dict[str, Any]] = []
    for r in records:
        fs = r.get("fetch_status") or {}
        if not fs:
            out.append(dict(r))  # shallow copy to avoid surprise mutations
            continue
        annotated = dict(r)
        for ct in fs:
            if ct in annotated:
                annotated[ct] = f"{annotated[ct]} *"
        out.append(annotated)
    return out


def render_records(
    records: list[dict[str, Any]],
    *,
    format_name: str | None,
    output: Path | None,
    columns: list[str] | None,
    footers: list[str] | None = None,
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
            return ExitCode.OUTPUT.value
        _print_table(records, cols)
        if footers:
            for line in footers:
                print(line)
        if not records:
            print("# 0 records", file=sys.stderr, flush=True)
        return ExitCode.OK.value

    if format_name == "json":
        body = json.dumps([_project(r, cols) for r in records], indent=2, default=str)
        if is_file:
            target = output if output.suffix == ".json" else output.with_suffix(".json")
            _atomic_write_text(target, body + "\n", encoding="utf-8")
        else:
            print(body, flush=True)
        if not records:
            print("# 0 records", file=sys.stderr, flush=True)
        return ExitCode.OK.value

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
        return ExitCode.OK.value

    print(f"error: unknown format {format_name!r}", file=sys.stderr, flush=True)
    return ExitCode.OUTPUT.value


def _derive_columns(records: list[dict[str, Any]]) -> list[str]:
    if not records:
        return []
    return list(records[0].keys())


def _project(record: dict[str, Any], cols: list[str]) -> dict[str, Any]:
    """Project record to columns, omitting keys absent from the record.

    Returns a dict with `cols` ordering for present keys only. Records that
    explicitly contain a key with value None still emit `c: None`; records
    that are silent on a key (key not in dict) skip it entirely.

    This honors the spec contract: optional fields like `fetch_status` (only
    populated for non-healthy records) appear in JSON output only when
    populated; absent in healthy-record dicts.
    """
    return {c: record[c] for c in cols if c in record}


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
