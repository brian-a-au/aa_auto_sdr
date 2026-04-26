#!/usr/bin/env python3
"""Build sample_outputs/ from tests/fixtures/sample_rs.json. Deterministic.

Re-running the script produces a byte-identical tree. tests/test_sample_outputs.py
asserts the committed sample_outputs/ matches what the script currently produces."""

from __future__ import annotations

import json
import re
import shutil
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "sample_rs.json"
OUT = REPO / "sample_outputs"

# Fixed timestamps (otherwise xlsxwriter / captured_at drift on every run).
FIXED_CAPTURED_AT_A = datetime(2026, 4, 1, 12, 0, 0, tzinfo=UTC)
FIXED_CAPTURED_AT_B = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
FIXED_TOOL_VERSION = "1.0.0"


def _df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


def _build_mock_client():
    """Build a MagicMock client whose handle returns the fixture data."""
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])

    from aa_auto_sdr.api.client import AaClient

    return AaClient(handle=handle, company_id="testco")


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


_README_TEXT = """# Sample Outputs

These files demonstrate every output format `aa_auto_sdr` produces. They are
generated from a fixed test fixture (`tests/fixtures/sample_rs.json`) — no real
Adobe Analytics data is committed here.

## Regenerate

```bash
uv run python scripts/build_sample_outputs.py
```

The script is deterministic: re-running produces byte-identical files. CI
asserts the committed tree matches the script's current output via
`tests/test_sample_outputs.py`.

## Files

### Generation outputs (one report suite, one timestamp)

| File | Format | Notes |
|---|---|---|
| `demo_prod.xlsx` | Excel | One sheet per component type. *Best-effort sample only — xlsxwriter embeds creation time in zip metadata, so the file is not byte-deterministic across runs and is excluded from the up-to-date assertion test.* |
| `demo_prod.json` | JSON | Full SdrDocument as JSON. |
| `demo_prod.html` | HTML | Single self-contained file with inline CSS. |
| `demo_prod.md` | Markdown | GFM-flavored. |
| `demo_prod.<component>.csv` | CSV | One file per component type (seven files). |

### Diff outputs

Two synthetic snapshots (`synthetic_snapshot_a.json` and `_b.json`) differ by
one renamed dimension and one removed metric. The diff is rendered three ways:

| File | Renderer |
|---|---|
| `diff_console.txt` | Console (ANSI escapes stripped for repo display) |
| `diff_report.json` | JSON renderer (sorted keys, jq-friendly) |
| `diff_report.md` | Markdown renderer (GFM tables, PR-comment-friendly) |
"""


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()

    from aa_auto_sdr.output import registry
    from aa_auto_sdr.output.diff_renderers.console import render_console
    from aa_auto_sdr.output.diff_renderers.json import render_json as render_diff_json
    from aa_auto_sdr.output.diff_renderers.markdown import render_markdown as render_diff_md
    from aa_auto_sdr.sdr.builder import build_sdr
    from aa_auto_sdr.snapshot.comparator import compare
    from aa_auto_sdr.snapshot.schema import document_to_envelope

    registry.bootstrap()
    client = _build_mock_client()

    # Build the SdrDocument once at the FIXED_CAPTURED_AT_B timestamp.
    doc = build_sdr(client, "demo.prod", captured_at=FIXED_CAPTURED_AT_B, tool_version=FIXED_TOOL_VERSION)

    # Five format outputs.
    for fmt in ("excel", "csv", "json", "html", "markdown"):
        writer = registry.get_writer(fmt)
        target = OUT / f"demo_prod{writer.extension}"
        writer.write(doc, target)

    # Two synthetic divergent snapshots.
    envelope_a_doc = build_sdr(client, "demo.prod", captured_at=FIXED_CAPTURED_AT_A, tool_version=FIXED_TOOL_VERSION)
    env_a = document_to_envelope(envelope_a_doc)

    env_b = deepcopy(env_a)
    env_b["captured_at"] = FIXED_CAPTURED_AT_B.isoformat()
    if env_b["components"]["dimensions"]:
        env_b["components"]["dimensions"][0] = {
            **env_b["components"]["dimensions"][0],
            "name": env_b["components"]["dimensions"][0].get("name", "") + " (renamed)",
        }
    if env_b["components"]["metrics"]:
        env_b["components"]["metrics"] = env_b["components"]["metrics"][1:]

    # Explicit utf-8 — Windows' default 'charmap' codec cannot encode `→` and other unicode
    (OUT / "synthetic_snapshot_a.json").write_text(json.dumps(env_a, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "synthetic_snapshot_b.json").write_text(json.dumps(env_b, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = compare(env_a, env_b)
    (OUT / "diff_console.txt").write_text(_strip_ansi(render_console(report)), encoding="utf-8")
    (OUT / "diff_report.json").write_text(render_diff_json(report), encoding="utf-8")
    (OUT / "diff_report.md").write_text(render_diff_md(report), encoding="utf-8")

    (OUT / "README.md").write_text(_README_TEXT, encoding="utf-8")

    print(f"sample_outputs/ generated at {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
