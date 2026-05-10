"""Console renderer for TrendingReport — table per RSID with drift footer."""

from __future__ import annotations

from io import StringIO

from aa_auto_sdr.snapshot.trending import TrendingReport

_COMPONENT_TYPE_ABBREV = {
    "dimensions": "dim",
    "metrics": "met",
    "segments": "seg",
    "calculated_metrics": "cal",
    "virtual_report_suites": "vrs",
    "classifications": "cls",
}


def render_console(reports: list[TrendingReport]) -> str:
    """Render one or more TrendingReports as a human-readable table.

    Each report gets its own block; multi-RSID invocations render blocks
    separated by blank lines. Output is text — caller handles writing
    to stdout / file.
    """
    out = StringIO()
    for i, report in enumerate(reports):
        if i > 0:
            out.write("\n")
        _render_one(report, out)
    return out.getvalue()


def _render_one(report: TrendingReport, out: StringIO) -> None:
    name_part = f" — {report.name}" if report.name else ""
    out.write(f"TRENDING WINDOW ({report.rsid}{name_part})\n")
    out.write(
        f"Window: {report.window.duration} "
        f"({report.window.start_at.isoformat()} → {report.window.end_at.isoformat()})\n",
    )
    out.write(f"Snapshots: {len(report.series)}\n\n")

    if not report.series:
        out.write("(no snapshots in window)\n")
        return

    # Header: timestamp + 6 component-count cols + 3 delta cols.
    out.write(
        f"{'Captured (UTC)':<20}  "
        f"{'dim':>5} {'met':>5} {'seg':>5} {'cal':>5} {'vrs':>5} {'cls':>5}  "
        f"{'Δadd':>5} {'Δrem':>5} {'Δmod':>5}\n",
    )
    for point in report.series:
        ts = point.captured_at.strftime("%Y-%m-%dT%H:%M")
        c = point.counts
        if point.delta_by_type is None:
            d_add: int | str = "—"
            d_rem: int | str = "—"
            d_mod: int | str = "—"
        else:
            d_add = sum(d.added for d in point.delta_by_type.values())
            d_rem = sum(d.removed for d in point.delta_by_type.values())
            d_mod = sum(d.modified for d in point.delta_by_type.values())
        out.write(
            f"{ts:<20}  "
            f"{c.dimensions:>5} {c.metrics:>5} {c.segments:>5} "
            f"{c.calculated_metrics:>5} {c.virtual_report_suites:>5} {c.classifications:>5}  "
            f"{d_add:>5} {d_rem:>5} {d_mod:>5}\n",
        )

    # Drift summary footer.
    out.write("\nDRIFT SUMMARY\n")
    drift = report.drift
    if drift is None:
        out.write("(drift not computed)\n")
        return
    out.write(f"Total changes:           {drift.total_changes}\n")
    out.write(
        f"Volatility score:        {drift.volatility_score:.3f}  (0.0=stable, 1.0=fully churned per pair)\n",
    )
    out.write(f"Most active type:        {drift.most_active_component_type or '—'}\n")
    churn = drift.churn_by_component_type
    churn_str = "  ".join(f"{_COMPONENT_TYPE_ABBREV[ct]}:{churn.get(ct, 0)}" for ct in _COMPONENT_TYPE_ABBREV)
    out.write(f"Churn by type:           {churn_str}\n")
