"""Invocation-owned lookup tables over a preloaded report-suite listing."""

from __future__ import annotations

from typing import Any


class ReportSuiteIndex:
    """Retain raw rows; only materialize IDs/names after a matching lookup.

    Unusual SDK values use the existing scan rather than acquiring new hashing
    or string-conversion behavior. No rows are copied or retained across runs.
    """

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.rsids: set[str] = set()
        self.exact_names: dict[str, list[dict[str, Any]]] = {}
        self.folded_names: dict[str, list[dict[str, Any]]] = {}
        self.scan_rsids = False
        self.scan_names = False
        for raw in rows:
            if type(raw) is not dict:
                self.scan_rsids = self.scan_names = True
                return
            rsid = raw.get("rsid")
            if type(rsid) is str:
                self.rsids.add(rsid)
            elif rsid is not None:
                self.scan_rsids = True
            name = raw.get("name")
            if type(name) is str:
                self.exact_names.setdefault(name, []).append(raw)
                self.folded_names.setdefault(name.casefold(), []).append(raw)
            elif name is not None:
                self.scan_names = True
