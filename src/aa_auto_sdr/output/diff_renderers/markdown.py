"""DiffReport → GitHub-flavored Markdown.

Tables for added / removed / modified per component type. Empty sections
are omitted (no '## Metrics (no changes)' clutter). Pipe characters are
escaped via the existing output._helpers.escape_pipe."""

from __future__ import annotations

from io import StringIO

from aa_auto_sdr.output._helpers import escape_pipe, stringify_cell
from aa_auto_sdr.snapshot.models import ComponentDiff, DiffReport

_TYPE_LABELS = {
    "dimensions": "Dimensions",
    "metrics": "Metrics",
    "segments": "Segments",
    "calculated_metrics": "Calculated Metrics",
    "virtual_report_suites": "Virtual Report Suites",
    "classifications": "Classifications",
}


def render_markdown(report: DiffReport) -> str:
    buf = StringIO()
    buf.write("# SDR Diff\n\n")
    buf.write(
        f"**Source:** `{report.a_rsid}` @ `{report.a_captured_at}` (tool {report.a_tool_version})\n",
    )
    buf.write(
        f"**Target:** `{report.b_rsid}` @ `{report.b_captured_at}` (tool {report.b_tool_version})\n\n",
    )
    if report.rsid_mismatch:
        buf.write(f"> ⚠️ RSID mismatch: source `{report.a_rsid}` ≠ target `{report.b_rsid}`\n\n")

    if report.report_suite_deltas:
        buf.write("## Report Suite\n\n")
        buf.write("| Field | Before | After |\n|---|---|---|\n")
        for d in report.report_suite_deltas:
            buf.write(
                f"| `{escape_pipe(d.field)}` "
                f"| {escape_pipe(stringify_cell(d.before))} "
                f"| {escape_pipe(stringify_cell(d.after))} |\n",
            )
        buf.write("\n")

    for cd in report.components:
        if not (cd.added or cd.removed or cd.modified):
            continue
        _render_component_section(buf, cd)

    return buf.getvalue()


def _render_component_section(buf: StringIO, cd: ComponentDiff) -> None:
    label = _TYPE_LABELS.get(cd.component_type, cd.component_type)
    counts = f"+{len(cd.added)} / -{len(cd.removed)} / ~{len(cd.modified)} / {cd.unchanged_count} unchanged"
    buf.write(f"## {label} ({counts})\n\n")

    if cd.added:
        buf.write("### Added\n\n| ID | Name |\n|---|---|\n")
        for item in cd.added:
            buf.write(f"| {escape_pipe(item.id)} | {escape_pipe(item.name)} |\n")
        buf.write("\n")

    if cd.removed:
        buf.write("### Removed\n\n| ID | Name |\n|---|---|\n")
        for item in cd.removed:
            buf.write(f"| {escape_pipe(item.id)} | {escape_pipe(item.name)} |\n")
        buf.write("\n")

    if cd.modified:
        buf.write("### Modified\n\n| ID | Name | Field | Before | After |\n|---|---|---|---|---|\n")
        for item in cd.modified:
            for delta in item.deltas:
                buf.write(
                    f"| {escape_pipe(item.id)} "
                    f"| {escape_pipe(item.name)} "
                    f"| `{escape_pipe(delta.field)}` "
                    f"| {escape_pipe(stringify_cell(delta.before))} "
                    f"| {escape_pipe(stringify_cell(delta.after))} |\n",
                )
        buf.write("\n")
