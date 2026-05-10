"""Markdown renderer for TrendingReport — heading + table + drift section."""

from __future__ import annotations

from io import StringIO

from aa_auto_sdr.snapshot.trending import TrendingReport


def render_markdown(reports: list[TrendingReport]) -> str:
    """Render TrendingReport(s) as Markdown (governance / Slack / GitHub Step Summary)."""
    out = StringIO()
    for i, report in enumerate(reports):
        if i > 0:
            out.write("\n---\n\n")
        _render_one(report, out)
    return out.getvalue()


def _render_one(report: TrendingReport, out: StringIO) -> None:
    name_part = f" — {report.name}" if report.name else ""
    out.write(f"# Trending: {report.rsid}{name_part}\n\n")
    out.write(f"**Window:** {report.window.duration} ")
    out.write(f"({report.window.start_at.isoformat()} → {report.window.end_at.isoformat()})\n")
    out.write(f"**Snapshots:** {len(report.series)}\n\n")

    if not report.series:
        out.write("_No snapshots in window._\n")
        return

    out.write("| Captured | dim | met | seg | cal | vrs | cls | Δadd | Δrem | Δmod |\n")
    out.write("|----------|-----|-----|-----|-----|-----|-----|------|------|------|\n")
    for point in report.series:
        ts = point.captured_at.strftime("%Y-%m-%dT%H:%M")
        c = point.counts
        if point.delta_by_type is None:
            d_add = d_rem = d_mod = "—"
        else:
            d_add = str(sum(d.added for d in point.delta_by_type.values()))
            d_rem = str(sum(d.removed for d in point.delta_by_type.values()))
            d_mod = str(sum(d.modified for d in point.delta_by_type.values()))
        out.write(
            f"| {ts} | {c.dimensions} | {c.metrics} | {c.segments} | "
            f"{c.calculated_metrics} | {c.virtual_report_suites} | {c.classifications} | "
            f"{d_add} | {d_rem} | {d_mod} |\n",
        )

    out.write("\n## Drift\n\n")
    drift = report.drift
    if drift is None:
        out.write("_Drift not computed._\n")
        return
    out.write(f"- **Total changes:** {drift.total_changes}\n")
    out.write(
        f"- **Volatility score:** {drift.volatility_score:.3f} (0.0=stable, 1.0=fully churned per pair)\n",
    )
    out.write(f"- **Most active type:** {drift.most_active_component_type or '—'}\n")
    out.write("- **Churn by type:**\n")
    out.writelines(f"  - {ct}: {count}\n" for ct, count in drift.churn_by_component_type.items())
