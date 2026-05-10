"""JSON renderer for TrendingReport — schema 'aa-trending/v1'."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from aa_auto_sdr.snapshot.trending import TrendingReport

_SCHEMA = "aa-trending/v1"


def render_json(reports: list[TrendingReport]) -> str:
    """Serialize TrendingReport(s) to a JSON string.

    Single-RSID: {"schema": ..., "rsid": ..., "window": ..., "series": [...], "drift": ...}.
    Multi-RSID: {"schema": ..., "reports": [{...rsid 1...}, {...rsid 2...}]}.
    """
    if len(reports) == 1:
        payload: dict[str, Any] = {"schema": _SCHEMA, **_to_dict(reports[0])}
    else:
        payload = {"schema": _SCHEMA, "reports": [_to_dict(r) for r in reports]}
    return json.dumps(payload, sort_keys=True, indent=2, default=_json_default) + "\n"


def _to_dict(report: TrendingReport) -> dict[str, Any]:
    """Convert TrendingReport to a JSON-serializable dict.

    `asdict` handles nested dataclasses; datetime fields go through
    `_json_default`.
    """
    return asdict(report)


def _json_default(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"object of type {type(obj).__name__} is not JSON serializable")
