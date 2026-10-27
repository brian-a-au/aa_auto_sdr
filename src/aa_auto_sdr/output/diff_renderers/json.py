"""DiffReport → JSON string. Stable shape via dataclasses.asdict + sort_keys."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from aa_auto_sdr.snapshot.diff_coverage import diff_coverage
from aa_auto_sdr.snapshot.models import DiffReport


def render_json(
    report: DiffReport,
    *,
    summary: bool = False,
    labels: tuple[str, str] | None = None,
    coverage: dict[str, Any] | None = None,
) -> str:
    """Render the report. `coverage` is the top-level `coverage` object
    (see snapshot.diff_coverage); when omitted it is derived from `report`
    with the default compare options."""
    payload = dataclasses.asdict(report)
    payload["coverage"] = coverage if coverage is not None else diff_coverage(report)
    if labels:
        payload["a_label"] = labels[0]
        payload["b_label"] = labels[1]
    if summary:
        # In summary mode, strip per-field deltas from modified entries and
        # drop the report-suite header deltas. The shape stays stable —
        # modified entries are still listed, just with empty `deltas`.
        for c in payload.get("components", []):
            for m in c.get("modified", []):
                m["deltas"] = []
        payload["report_suite_deltas"] = []
    return json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
