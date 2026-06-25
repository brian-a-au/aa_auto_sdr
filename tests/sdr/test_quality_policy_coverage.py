"""Coverage for error/edge branches in sdr/quality_policy.py.

Covers the non-object top-level JSON rejection, the unknown-key rejection,
the CSV-to-stdout path, and the unsupported-format guard in
write_quality_report.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.sdr.quality import Issue, SeverityLevel
from aa_auto_sdr.sdr.quality_policy import load_policy, write_quality_report


def test_load_policy_rejects_non_object_top_level(tmp_path: Path) -> None:
    p = tmp_path / "policy.json"
    p.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(ConfigError, match="expected JSON object"):
        load_policy(p)


def test_load_policy_rejects_unknown_top_level_key(tmp_path: Path) -> None:
    p = tmp_path / "policy.json"
    p.write_text(json.dumps({"bogus_key": 1}))
    with pytest.raises(ConfigError, match="unknown top-level key"):
        load_policy(p)


def test_write_quality_report_csv_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    issues = [Issue(SeverityLevel.LOW, "naming", "version_suffix", "evar6", "v_v2", "x", {})]
    write_quality_report(issues=issues, summary={"total": 1}, target="-", fmt="csv")
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0] == "severity,category,type,item_id,item_name,issue"
    assert lines[1].startswith("LOW,naming,version_suffix,")


def test_write_quality_report_rejects_unsupported_format(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="unsupported quality-report format"):
        write_quality_report(
            issues=[],
            summary={"total": 0},
            target=tmp_path / "report.out",
            fmt="xml",  # type: ignore[arg-type]
        )
