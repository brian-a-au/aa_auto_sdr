"""DiffReport → JSON string. Stable shape via dataclasses.asdict + sort_keys."""

from __future__ import annotations

import dataclasses
import json

from aa_auto_sdr.snapshot.models import DiffReport


def render_json(report: DiffReport, *, summary: bool = False) -> str:
    payload = dataclasses.asdict(report)
    if summary:
        # In summary mode, strip per-field deltas from modified entries and
        # drop the report-suite header deltas. The shape stays stable —
        # modified entries are still listed, just with empty `deltas`.
        for c in payload.get("components", []):
            for m in c.get("modified", []):
                m["deltas"] = []
        payload["report_suite_deltas"] = []
    return json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
