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


def render_markdown(
    report: DiffReport,
    *,
    side_by_side: bool = False,
    summary: bool = False,
    quiet: bool = False,
    labels: tuple[str, str] | None = None,
) -> str:
    buf = StringIO()
    buf.write("# SDR Diff\n\n")
    a_label = labels[0] if labels else "Source"
    b_label = labels[1] if labels else "Target"
    buf.write(
        f"**{a_label}:** `{report.a_rsid}` @ `{report.a_captured_at}` (tool {report.a_tool_version})\n",
    )
    buf.write(
        f"**{b_label}:** `{report.b_rsid}` @ `{report.b_captured_at}` (tool {report.b_tool_version})\n\n",
    )
    if report.rsid_mismatch:
        buf.write(f"> ⚠️ RSID mismatch: source `{report.a_rsid}` ≠ target `{report.b_rsid}`\n\n")

    if summary:
        # Summary mode: per-component-type count rows, no per-item detail.
        buf.write("## Summary\n\n")
        if quiet:
            buf.write("| Component | Added | Removed | Modified |\n")
            buf.write("|---|---|---|---|\n")
            for cd in report.components:
                if not (cd.added or cd.removed or cd.modified):
                    continue
                label = _TYPE_LABELS.get(cd.component_type, cd.component_type)
                buf.write(
                    f"| {label} | {len(cd.added)} | {len(cd.removed)} | {len(cd.modified)} |\n",
                )
        else:
            buf.write("| Component | Added | Removed | Modified | Unchanged |\n")
            buf.write("|---|---|---|---|---|\n")
            for cd in report.components:
                label = _TYPE_LABELS.get(cd.component_type, cd.component_type)
                buf.write(
                    f"| {label} | {len(cd.added)} | {len(cd.removed)} | {len(cd.modified)} | {cd.unchanged_count} |\n",
                )
        buf.write("\n")
        return buf.getvalue()

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
        _render_component_section(buf, cd, side_by_side=side_by_side, quiet=quiet)

    return buf.getvalue()


def _render_component_section(
    buf: StringIO,
    cd: ComponentDiff,
    *,
    side_by_side: bool = False,
    quiet: bool = False,
) -> None:
    label = _TYPE_LABELS.get(cd.component_type, cd.component_type)
    if quiet:
        counts = f"+{len(cd.added)} / -{len(cd.removed)} / ~{len(cd.modified)}"
    else:
        counts = f"+{len(cd.added)} / -{len(cd.removed)} / ~{len(cd.modified)} / {cd.unchanged_count} unchanged"
    buf.write(f"## {label} ({counts})\n\n")

    if cd.added:
        buf.write("### Added\n\n| ID | Name |\n|---|---|\n")
        buf.writelines(f"| {escape_pipe(item.id)} | {escape_pipe(item.name)} |\n" for item in cd.added)
        buf.write("\n")

    if cd.removed:
        buf.write("### Removed\n\n| ID | Name |\n|---|---|\n")
        buf.writelines(f"| {escape_pipe(item.id)} | {escape_pipe(item.name)} |\n" for item in cd.removed)
        buf.write("\n")

    if cd.modified:
        # Both default and side_by_side currently emit the same flat 5-column table
        # with Before/After columns. The side_by_side flag is accepted for symmetry
        # with console.py and as a forward-compatibility hook; the default markdown
        # form is already a side-by-side layout.
        _ = side_by_side
        buf.write("### Modified\n\n| ID | Name | Field | Before | After |\n|---|---|---|---|---|\n")
        for item in cd.modified:
            buf.writelines(
                f"| {escape_pipe(item.id)} "
                f"| {escape_pipe(item.name)} "
                f"| `{escape_pipe(delta.field)}` "
                f"| {escape_pipe(stringify_cell(delta.before))} "
                f"| {escape_pipe(stringify_cell(delta.after))} |\n"
                for delta in item.deltas
            )
        buf.write("\n")
