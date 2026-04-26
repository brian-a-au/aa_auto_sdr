"""DiffReport → JSON string. Stable shape via dataclasses.asdict + sort_keys."""

from __future__ import annotations

import dataclasses
import json

from aa_auto_sdr.snapshot.models import DiffReport


def render_json(report: DiffReport) -> str:
    payload = dataclasses.asdict(report)
    return json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
