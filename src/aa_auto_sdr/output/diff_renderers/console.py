"""DiffReport → human-readable console output (banner-style, ANSI-colored).

Color via core/colors (auto-disabled for non-TTY / NO_COLOR=1). Banner width
from core/constants.BANNER_WIDTH (60, set in v0.5)."""

from __future__ import annotations

import json
from io import StringIO
from typing import Any

from aa_auto_sdr.core import colors
from aa_auto_sdr.core.constants import BANNER_WIDTH
from aa_auto_sdr.snapshot.models import ComponentDiff, DiffReport, ModifiedItem


def _fmt_value(v: Any) -> str:
    """Format a value for the console diff output. Strings get double quotes;
    None becomes 'null'; dict/list become compact JSON; everything else str()."""
    if isinstance(v, str):
        return f'"{v}"'
    if v is None:
        return "null"
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True, separators=(", ", ": "))
    return str(v)


_TYPE_LABELS = {
    "dimensions": "Dimensions",
    "metrics": "Metrics",
    "segments": "Segments",
    "calculated_metrics": "Calculated metrics",
    "virtual_report_suites": "Virtual report suites",
    "classifications": "Classifications",
}


def render_console(
    report: DiffReport,
    *,
    side_by_side: bool = False,
    summary: bool = False,
    quiet: bool = False,
    labels: tuple[str, str] | None = None,
) -> str:
    buf = StringIO()
    bar = "=" * BANNER_WIDTH
    buf.write(f"{bar}\n")
    buf.write(colors.bold("SDR DIFF") + "\n")
    buf.write(f"{bar}\n")
    a_label = labels[0] if labels else "Source"
    b_label = labels[1] if labels else "Target"
    buf.write(
        f"{a_label}: {report.a_rsid} @ {report.a_captured_at} (tool {report.a_tool_version})\n",
    )
    buf.write(
        f"{b_label}: {report.b_rsid} @ {report.b_captured_at} (tool {report.b_tool_version})\n",
    )
    if report.rsid_mismatch:
        buf.write(
            colors.warn(
                f"⚠ RSID mismatch: source {report.a_rsid} ≠ target {report.b_rsid}",
            )
            + "\n",
        )
    buf.write("\n")

    if summary:
        # Summary mode: per-component-type counts only.
        for cd in report.components:
            label = _TYPE_LABELS.get(cd.component_type, cd.component_type)
            if quiet and not (cd.added or cd.removed or cd.modified):
                continue
            buf.write(
                f"{label}: +{len(cd.added)} added, -{len(cd.removed)} removed, "
                f"~{len(cd.modified)} modified" + ("" if quiet else f", {cd.unchanged_count} unchanged") + "\n",
            )
        buf.write(f"{bar}\n")
        return buf.getvalue()

    if report.report_suite_deltas:
        buf.write(colors.bold("Report Suite header") + "\n")
        for d in report.report_suite_deltas:
            buf.write(f"  {colors.warn('~')} {d.field}: {_fmt_value(d.before)} → {_fmt_value(d.after)}\n")
        buf.write("\n")

    total_added = total_removed = total_modified = total_unchanged = 0
    for cd in report.components:
        if quiet and not (cd.added or cd.removed or cd.modified):
            total_unchanged += cd.unchanged_count
            continue
        _render_component(buf, cd, side_by_side=side_by_side, quiet=quiet)
        total_added += len(cd.added)
        total_removed += len(cd.removed)
        total_modified += len(cd.modified)
        total_unchanged += cd.unchanged_count

    buf.write(f"{bar}\n")
    if quiet:
        buf.write(
            f"Total: +{total_added} added, -{total_removed} removed, ~{total_modified} modified\n",
        )
    else:
        buf.write(
            f"Total: +{total_added} added, -{total_removed} removed, "
            f"~{total_modified} modified, {total_unchanged} unchanged\n",
        )
    buf.write(f"{bar}\n")
    return buf.getvalue()


def _render_component(
    buf: StringIO,
    cd: ComponentDiff,
    *,
    side_by_side: bool = False,
    quiet: bool = False,
) -> None:
    label = _TYPE_LABELS.get(cd.component_type, cd.component_type)
    if quiet:
        summary = f"+{len(cd.added)} added, -{len(cd.removed)} removed, ~{len(cd.modified)} modified"
    else:
        summary = (
            f"+{len(cd.added)} added, -{len(cd.removed)} removed, "
            f"~{len(cd.modified)} modified, {cd.unchanged_count} unchanged"
        )
    buf.write(f"{label}: {summary}\n")
    buf.writelines(f"  {colors.success('+')} {item.id} — {item.name}\n" for item in cd.added)
    buf.writelines(f"  {colors.error('-')} {item.id} — {item.name}\n" for item in cd.removed)
    for item in cd.modified:
        _render_modified_item(buf, item, side_by_side=side_by_side)
    if cd.added or cd.removed or cd.modified:
        buf.write("\n")


def _render_modified_item(buf: StringIO, item: ModifiedItem, *, side_by_side: bool = False) -> None:
    buf.write(f"  {colors.warn('~')} {item.id} — {item.name}\n")
    if side_by_side:
        for delta in item.deltas:
            before = _fmt_value(delta.before)
            after = _fmt_value(delta.after)
            buf.write(f"      {delta.field}:  {before}  |  {after}\n")
    else:
        buf.writelines(
            f"      {delta.field}: {_fmt_value(delta.before)} → {_fmt_value(delta.after)}\n" for delta in item.deltas
        )
