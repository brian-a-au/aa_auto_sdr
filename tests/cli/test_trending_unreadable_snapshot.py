"""One unreadable snapshot in the window is exit 16, not a traceback.

`compute_trending` loads every snapshot file whose name falls in the window,
and the handler caught no snapshot error. A corrupt file, a file that is not
JSON, or a file with an unsupported schema ended the run with a traceback and
exit 1. Diff reports the same conditions as SNAPSHOT (16), and the message
names the file so the user can fix or remove it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aa_auto_sdr.cli.commands import trending as cmd
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.snapshot.store import captured_at_to_filename


def _stem(hours_ago: int) -> str:
    """A filename stem inside the default 30d window the handler resolves."""
    moment = datetime.now(UTC) - timedelta(hours=hours_ago)
    return captured_at_to_filename(moment.isoformat()).removesuffix(".json")


_STEM = _stem(1)
_OLDER_STEM = _stem(25)


def _envelope(rsid: str = "demo.prod") -> dict:
    return {
        "schema": "aa-sdr-snapshot/v4",
        "rsid": rsid,
        "captured_at": "2026-04-26T17:29:01+00:00",
        "tool_version": "1.24.3",
        "degraded_components": [],
        "partial_components": {},
        "quality": None,
        "collected_components": [
            "calculated_metrics",
            "classifications",
            "dimensions",
            "metrics",
            "segments",
            "virtual_report_suites",
        ],
        "components": {
            "report_suite": {
                "rsid": rsid,
                "name": "Demo",
                "timezone": "UTC",
                "currency": "USD",
                "parent_rsid": None,
            },
            "dimensions": [],
            "metrics": [],
            "segments": [],
            "calculated_metrics": [],
            "virtual_report_suites": [],
            "classifications": [],
        },
    }


def _run(snapshot_dir: Path) -> int:
    return cmd.run(
        rsids=["demo.prod"],
        duration="30d",
        snapshot_dir=snapshot_dir,
        profile=None,
        format_name="json",
        output="-",
        extended_fields=False,
        ignore_fields=(),
    )


@pytest.fixture
def snapshot_dir(tmp_path: Path) -> Path:
    rs_dir = tmp_path / "demo.prod"
    rs_dir.mkdir(parents=True)
    (rs_dir / f"{_OLDER_STEM}.json").write_text(json.dumps(_envelope()), encoding="utf-8")
    return tmp_path


def _bad_file(snapshot_dir: Path) -> Path:
    return snapshot_dir / "demo.prod" / f"{_STEM}.json"


def test_unparseable_json_is_snapshot_exit_code(snapshot_dir: Path, capsys) -> None:
    _bad_file(snapshot_dir).write_text("{not json", encoding="utf-8")
    assert _run(snapshot_dir) == ExitCode.SNAPSHOT.value
    captured = capsys.readouterr()
    assert _STEM in captured.err
    assert captured.out == ""


def test_corrupt_envelope_is_snapshot_exit_code(snapshot_dir: Path, capsys) -> None:
    env = _envelope()
    del env["components"]["dimensions"][:]
    env["components"]["metrics"] = [{"name": "row with no id"}]
    _bad_file(snapshot_dir).write_text(json.dumps(env), encoding="utf-8")
    assert _run(snapshot_dir) == ExitCode.SNAPSHOT.value
    assert _STEM in capsys.readouterr().err


def test_unsupported_schema_is_snapshot_exit_code(snapshot_dir: Path, capsys) -> None:
    env = _envelope()
    env["schema"] = "aa-sdr-snapshot/v9"
    _bad_file(snapshot_dir).write_text(json.dumps(env), encoding="utf-8")
    assert _run(snapshot_dir) == ExitCode.SNAPSHOT.value
    assert _STEM in capsys.readouterr().err


def test_readable_window_still_succeeds(snapshot_dir: Path, capsys) -> None:
    _bad_file(snapshot_dir).write_text(json.dumps(_envelope()), encoding="utf-8")
    assert _run(snapshot_dir) == ExitCode.OK.value
    payload = json.loads(capsys.readouterr().out)
    assert payload["rsid"] == "demo.prod"
    assert len(payload["series"]) == 2
