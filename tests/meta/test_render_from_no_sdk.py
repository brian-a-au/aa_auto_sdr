"""--render-from is fully offline: the whole run must never import aanalytics2.

Runs a real render (every local format, so the heavy writer stack loads) in a
fresh interpreter with an import hook that refuses aanalytics2, then checks
sys.modules as well."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SDR_JSON = {
    "report_suite": {"rsid": "rs1", "name": "RS One", "timezone": None, "currency": None, "parent_rsid": None},
    "dimensions": [
        {
            "id": "variables/evar1",
            "name": "User",
            "type": "string",
            "category": None,
            "parent": "",
            "pathable": False,
            "description": None,
            "tags": [],
            "extra": {},
        }
    ],
    "metrics": [],
    "segments": [],
    "calculated_metrics": [],
    "virtual_report_suites": [],
    "classifications": [],
    "captured_at": "2026-04-25T17:30:00+00:00",
    "tool_version": "1.21.0",
    "fetch_status": {},
    "quality": None,
    "collected_components": None,
}

_CODE = """
import importlib.abc, sys

class _Refuse(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name == "aanalytics2" or name.startswith("aanalytics2."):
            raise ImportError("aanalytics2 must not load on the --render-from path")
        return None

sys.meta_path.insert(0, _Refuse())
from aa_auto_sdr.__main__ import main
rc = main(sys.argv[1:])
loaded = sorted(m for m in sys.modules if m == "aanalytics2" or m.startswith("aanalytics2."))
print("LOADED=" + ",".join(loaded))
sys.exit(rc)
"""


def test_render_from_never_imports_aanalytics2(tmp_path: Path) -> None:
    saved = tmp_path / "rs1.json"
    saved.write_text(json.dumps(_SDR_JSON))
    out = tmp_path / "out"
    env_clean = {k: v for k, v in os.environ.items() if k not in {"ORG_ID", "CLIENT_ID", "SECRET", "SCOPES"}}
    result = subprocess.run(
        [sys.executable, "-c", _CODE, "--render-from", str(saved), "--format", "all", "--output-dir", str(out)],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=env_clean,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "LOADED="
    assert (out / "rs1.xlsx").exists()
    assert (out / "rs1.md").exists()
