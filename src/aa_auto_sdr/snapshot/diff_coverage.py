"""What a snapshot diff compared, for the diff JSON `coverage` object.

Pure: derived from a DiffReport plus the compare and render options, so a
reader can judge the evidence behind a diff. Shape follows cja_auto_sdr's
diff coverage, with aa's own field and limitation names."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from aa_auto_sdr.api import models
from aa_auto_sdr.snapshot.comparator import _COMPONENT_TYPES, _EXTENDED_FIELDS_DEFAULT_IGNORE
from aa_auto_sdr.snapshot.models import DiffReport

# Settings changes are listed and counted in `settings_changes`, but never
# count toward --warn-threshold. (--watch treats them as triggers.)
SETTINGS_POLICY = "reported"

# Stable limitation IDs.
LIMITATION_THRESHOLD_COMPONENTS_ONLY = "warn_threshold_counts_components_only"
LIMITATION_BASELINE_BY_TIME = "baseline_chosen_by_time"
LIMITATION_EXCLUDED_NOT_COMPARED = "excluded_families_not_compared"
LIMITATION_SUPPRESSED_NOT_COMPARED = "suppressed_families_not_compared"
LIMITATION_SHOW_ONLY_THRESHOLD = "show_only_does_not_narrow_warn_threshold"

# Root-level identity keys: never reported as field deltas.
_IDENTITY_FIELDS = frozenset({"id", "rsid"})

_COMPONENT_MODELS: tuple[type, ...] = (
    models.Dimension,
    models.Metric,
    models.Segment,
    models.CalculatedMetric,
    models.VirtualReportSuite,
    models.ClassificationDataset,
)


def _field_names(*classes: type) -> set[str]:
    return {f.name for cls in classes for f in fields(cls)}


def effective_ignore_fields(ignore_fields: frozenset[str], *, extended_fields: bool) -> frozenset[str]:
    """The ignore set compare() applies: the user's set, plus the default set unless extended."""
    return ignore_fields if extended_fields else ignore_fields | _EXTENDED_FIELDS_DEFAULT_IGNORE


def diff_coverage(
    report: DiffReport,
    *,
    ignore_fields: frozenset[str] = frozenset(),
    extended_fields: bool = False,
    show_only: frozenset[str] = frozenset(),
    baseline_by_time: bool = False,
) -> dict[str, Any]:
    """Return the diff `coverage` object.

    `report` should be the full comparison (before render filters), so
    `limitations` reflect every family. `compare_fields` and `settings_fields`
    are the top-level model fields compared; keys nested under them are
    compared too, and the ignore set applies at every level."""
    ignored = effective_ignore_fields(ignore_fields, extended_fields=extended_fields)
    compare_fields = sorted(_field_names(*_COMPONENT_MODELS) - _IDENTITY_FIELDS - ignored)
    settings_fields = sorted(_field_names(models.ReportSuite) - _IDENTITY_FIELDS - ignored)

    limitations = [LIMITATION_THRESHOLD_COMPONENTS_ONLY]
    if baseline_by_time:
        limitations.append(LIMITATION_BASELINE_BY_TIME)
    comparability = {c.comparability for c in report.components}
    if "excluded" in comparability:
        limitations.append(LIMITATION_EXCLUDED_NOT_COMPARED)
    if comparability & {"unknown", "degraded", "partial"}:
        limitations.append(LIMITATION_SUPPRESSED_NOT_COMPARED)
    if show_only:
        limitations.append(LIMITATION_SHOW_ONLY_THRESHOLD)

    return {
        "compare_fields": compare_fields,
        "ignored_fields": sorted(ignored),
        "component_types": list(_COMPONENT_TYPES),
        "settings_fields": settings_fields,
        "settings_policy": SETTINGS_POLICY,
        "show_only": sorted(show_only) if show_only else None,
        "limitations": limitations,
    }
