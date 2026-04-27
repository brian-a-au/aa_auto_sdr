"""Pure post-compare filters for diff renderers.

The canonical DiffReport from snapshot.comparator stays intact — these filters
produce a render-time copy. JSON renderers may opt out of filtering to preserve
the full report for downstream consumers."""

from __future__ import annotations

from dataclasses import replace

from aa_auto_sdr.snapshot.models import ComponentDiff, DiffReport


def filter_for_render(
    report: DiffReport,
    *,
    changes_only: bool = False,
    show_only: frozenset[str] = frozenset(),
    max_issues: int | None = None,
) -> DiffReport:
    """Return a copy of `report` with presentational filters applied.

    - `changes_only` drops component types with no added/removed/modified entries.
    - `show_only` restricts to the named component types (empty set = no restriction).
    - `max_issues` caps each component's added/removed/modified lists to N items.

    Input is not mutated."""
    components: list[ComponentDiff] = []
    for cd in report.components:
        if show_only and cd.component_type not in show_only:
            continue
        if changes_only and not (cd.added or cd.removed or cd.modified):
            continue
        if max_issues is not None:
            capped = replace(
                cd,
                added=cd.added[:max_issues],
                removed=cd.removed[:max_issues],
                modified=cd.modified[:max_issues],
            )
            components.append(capped)
        else:
            components.append(cd)
    return replace(report, components=components)
