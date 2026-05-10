"""QualityPolicy loader + writer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.sdr.quality import Issue, SeverityLevel
from aa_auto_sdr.sdr.quality_policy import (
    QualityPolicy,
    apply_policy_defaults,
    load_policy,
)


class TestLoadPolicyHappyPath:
    def test_basic_flat(self, tmp_path: Path) -> None:
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"fail_on_quality": "HIGH", "quality_report": "json"}))
        policy = load_policy(p)
        assert policy.fail_on_quality == SeverityLevel.HIGH
        assert policy.quality_report == "json"

    def test_hyphen_keys_canonicalized(self, tmp_path: Path) -> None:
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"fail-on-quality": "MEDIUM", "quality-report": "csv"}))
        policy = load_policy(p)
        assert policy.fail_on_quality == SeverityLevel.MEDIUM
        assert policy.quality_report == "csv"

    def test_nested_under_quality_policy_envelope(self, tmp_path: Path) -> None:
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"quality_policy": {"fail_on_quality": "LOW"}}))
        policy = load_policy(p)
        assert policy.fail_on_quality == SeverityLevel.LOW

    def test_nested_under_quality_envelope(self, tmp_path: Path) -> None:
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"quality": {"fail_on_quality": "INFO"}}))
        policy = load_policy(p)
        assert policy.fail_on_quality == SeverityLevel.INFO


class TestLoadPolicyErrors:
    def test_path_does_not_exist(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_policy(tmp_path / "missing.json")

    def test_invalid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{not json")
        with pytest.raises(ConfigError, match="parse"):
            load_policy(p)

    def test_unknown_top_level_key_max_issues(self, tmp_path: Path) -> None:
        """Spec §2.2: max_issues is dropped from the policy schema."""
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"max_issues": 100}))
        with pytest.raises(ConfigError, match="max_issues"):
            load_policy(p)

    def test_unknown_top_level_key_allow_partial(self, tmp_path: Path) -> None:
        """Spec §2.2: allow_partial is dropped from the policy schema."""
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"allow_partial": True}))
        with pytest.raises(ConfigError, match="allow_partial"):
            load_policy(p)

    def test_invalid_severity_value(self, tmp_path: Path) -> None:
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"fail_on_quality": "EXTREME"}))
        with pytest.raises(ConfigError, match=r"severity|fail_on_quality"):
            load_policy(p)

    def test_invalid_report_format(self, tmp_path: Path) -> None:
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"quality_report": "excel"}))
        with pytest.raises(ConfigError, match=r"format|quality_report"):
            load_policy(p)


class TestApplyPolicyDefaults:
    def test_cli_wins_over_policy(self) -> None:
        import argparse

        ns = argparse.Namespace(fail_on_quality="LOW", quality_report=None)
        policy = QualityPolicy(fail_on_quality=SeverityLevel.HIGH, quality_report="json")
        result = apply_policy_defaults(
            cli_namespace=ns,
            policy=policy,
            explicitly_set={"fail_on_quality"},  # CLI passed --fail-on-quality LOW
        )
        # CLI wins — fail_on_quality stays "LOW"
        assert result.fail_on_quality == "LOW"
        # Policy fills the unset one
        assert result.quality_report == "json"

    def test_policy_fills_when_cli_unset(self) -> None:
        import argparse

        ns = argparse.Namespace(fail_on_quality=None, quality_report=None)
        policy = QualityPolicy(fail_on_quality=SeverityLevel.HIGH, quality_report="json")
        result = apply_policy_defaults(cli_namespace=ns, policy=policy, explicitly_set=set())
        assert result.fail_on_quality == "HIGH"
        assert result.quality_report == "json"


class TestWriteQualityReport:
    def test_json_writes_issues_and_summary(self, tmp_path: Path) -> None:
        from aa_auto_sdr.sdr.quality_policy import write_quality_report

        target = tmp_path / "report.json"
        issues = [Issue(SeverityLevel.HIGH, "naming", "stale_keyword", "evar5", "v_test", "x", {})]
        summary = {"by_severity": {"HIGH": 1}, "total": 1, "verdict": "fail"}
        write_quality_report(issues=issues, summary=summary, target=target, fmt="json")
        payload = json.loads(target.read_text())
        assert payload["summary"]["total"] == 1
        assert payload["issues"][0]["severity"] == "HIGH"

    def test_csv_writes_header_and_rows(self, tmp_path: Path) -> None:
        from aa_auto_sdr.sdr.quality_policy import write_quality_report

        target = tmp_path / "report.csv"
        issues = [Issue(SeverityLevel.LOW, "naming", "version_suffix", "evar6", "v_v2", "x", {})]
        write_quality_report(issues=issues, summary={"total": 1}, target=target, fmt="csv")
        lines = target.read_text().splitlines()
        assert lines[0] == "severity,category,type,item_id,item_name,issue"
        assert lines[1].startswith("LOW,naming,version_suffix,")

    def test_stdout_target(self, capsys: pytest.CaptureFixture[str]) -> None:
        from aa_auto_sdr.sdr.quality_policy import write_quality_report

        write_quality_report(issues=[], summary={"total": 0}, target="-", fmt="json")
        out = capsys.readouterr().out
        assert json.loads(out)["summary"]["total"] == 0
