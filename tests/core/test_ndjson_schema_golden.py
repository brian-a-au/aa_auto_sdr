"""v1.4 — pin the NDJSON record schema for run_complete. The full set of
keys (not values) must match the golden fixture exactly. Values like
timestamps, run_id, and duration_ms vary per-run and are excluded from the
compare. ``message`` is also volatile because it embeds the duration
(``run_complete exit_code=N duration_ms=M``); aggregators key off the
structured fields, not the human-readable line."""

from __future__ import annotations

import json
from pathlib import Path

from aa_auto_sdr.cli.main import run

GOLDEN = Path(__file__).parent.parent / "fixtures" / "logging" / "ndjson_run_complete_golden.json"
VOLATILE_KEYS = {"timestamp", "run_id", "duration_ms", "message"}


def _strip_volatile(record: dict) -> dict:
    return {k: v for k, v in record.items() if k not in VOLATILE_KEYS}


def test_run_complete_ndjson_matches_golden_schema(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # --show-config = no auth, deterministic exit. Emits run_start +
    # run_complete via cli/main.run.
    run(["--show-config", "--log-format", "json"])

    log_files = list((tmp_path / "logs").glob("*.log"))
    assert len(log_files) == 1
    lines = log_files[0].read_text().splitlines()
    records = [json.loads(line) for line in lines if line.strip()]
    completes = [r for r in records if "run_complete" in r.get("message", "")]
    assert len(completes) == 1
    actual = _strip_volatile(completes[0])

    golden = json.loads(GOLDEN.read_text())
    expected = _strip_volatile(golden)

    # Compare by key sets first (clearer error message), then full equality.
    assert set(actual) == set(expected), (
        f"NDJSON schema drift. Missing: {set(expected) - set(actual)}, extra: {set(actual) - set(expected)}."
    )
    # Value compare on non-volatile keys only.
    for k in actual:
        assert actual[k] == expected[k], f"Field {k!r}: {actual[k]!r} != {expected[k]!r}"
