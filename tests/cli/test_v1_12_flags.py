"""CLI argparse + dispatch wiring for v1.12.0 quality-engine flags."""

from __future__ import annotations

from pathlib import Path

import pytest

from aa_auto_sdr.cli.parser import build_parser


class TestQualityFlagDefaults:
    def test_quality_report_default_none(self) -> None:
        ns = build_parser().parse_args(["rs1"])
        assert ns.quality_report is None

    def test_quality_policy_default_none(self) -> None:
        ns = build_parser().parse_args(["rs1"])
        assert ns.quality_policy is None

    def test_fail_on_quality_default_none(self) -> None:
        ns = build_parser().parse_args(["rs1"])
        assert ns.fail_on_quality is None


class TestQualityReportChoices:
    def test_json_accepted(self) -> None:
        ns = build_parser().parse_args(["rs1", "--quality-report", "json"])
        assert ns.quality_report == "json"

    def test_csv_accepted(self) -> None:
        ns = build_parser().parse_args(["rs1", "--quality-report", "csv"])
        assert ns.quality_report == "csv"

    @pytest.mark.parametrize("bad", ["excel", "html", "markdown", "all", "yaml"])
    def test_disallowed_format_rejected(self, bad: str) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["rs1", "--quality-report", bad])


class TestFailOnQualityChoices:
    @pytest.mark.parametrize("sev", ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"])
    def test_severity_accepted(self, sev: str) -> None:
        ns = build_parser().parse_args(["rs1", "--fail-on-quality", sev])
        assert ns.fail_on_quality == sev

    def test_lowercase_rejected(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["rs1", "--fail-on-quality", "high"])

    def test_unknown_severity_rejected(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["rs1", "--fail-on-quality", "EXTREME"])


class TestQualityPolicyAcceptsPath:
    def test_path_arg(self, tmp_path: Path) -> None:
        p = tmp_path / "policy.json"
        ns = build_parser().parse_args(["rs1", "--quality-policy", str(p)])
        assert ns.quality_policy == p


class TestDroppedPolicyKeys:
    """Spec §2.2: max_issues and allow_partial are dropped from the policy
    schema (not CLI flags). The policy loader rejects them; verified by
    tests/sdr/test_quality_policy.py.

    Note: `--max-issues` is an unrelated diff-render cap (predates v1.12.0)
    and remains a valid CLI flag — it has no quality-engine semantics.
    `--allow-partial` is not an aa flag.
    """

    def test_allow_partial_rejected_as_cli_flag(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["rs1", "--allow-partial"])


class TestQualityAutoEnableLog:
    """Spec §3.12: `quality_auto_enabled` log fires when --quality-report or
    --fail-on-quality is set without --audit-naming / --flag-stale."""

    def test_auto_enable_emits_log_when_quality_report_alone(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import argparse
        import logging

        from aa_auto_sdr.cli import main as cli_main

        ns = argparse.Namespace(
            quality_report="json",
            fail_on_quality=None,
            audit_naming=False,
            flag_stale=False,
        )
        with caplog.at_level(logging.INFO, logger=cli_main.logger.name):
            cli_main._apply_quality_auto_enable(ns)

        assert ns.audit_naming is True
        assert ns.flag_stale is True
        events = [r for r in caplog.records if "quality_auto_enabled" in r.getMessage()]
        assert len(events) == 1
        assert getattr(events[0], "audit_naming", None) is True
        assert getattr(events[0], "flag_stale", None) is True

    def test_auto_enable_emits_log_when_fail_on_quality_alone(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import argparse
        import logging

        from aa_auto_sdr.cli import main as cli_main

        ns = argparse.Namespace(
            quality_report=None,
            fail_on_quality="HIGH",
            audit_naming=False,
            flag_stale=False,
        )
        with caplog.at_level(logging.INFO, logger=cli_main.logger.name):
            cli_main._apply_quality_auto_enable(ns)
        assert any("quality_auto_enabled" in r.getMessage() for r in caplog.records)
        assert ns.audit_naming is True
        assert ns.flag_stale is True

    def test_no_auto_enable_log_when_audits_already_on(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import argparse
        import logging

        from aa_auto_sdr.cli import main as cli_main

        ns = argparse.Namespace(
            quality_report="json",
            fail_on_quality=None,
            audit_naming=True,  # already on — auto-enable should be a no-op
            flag_stale=False,
        )
        with caplog.at_level(logging.INFO, logger=cli_main.logger.name):
            cli_main._apply_quality_auto_enable(ns)
        assert not any("quality_auto_enabled" in r.getMessage() for r in caplog.records)

    def test_no_auto_enable_log_when_no_quality_flags(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        import argparse
        import logging

        from aa_auto_sdr.cli import main as cli_main

        ns = argparse.Namespace(
            quality_report=None,
            fail_on_quality=None,
            audit_naming=False,
            flag_stale=False,
        )
        with caplog.at_level(logging.INFO, logger=cli_main.logger.name):
            cli_main._apply_quality_auto_enable(ns)
        assert not any("quality_auto_enabled" in r.getMessage() for r in caplog.records)
        assert ns.audit_naming is False
        assert ns.flag_stale is False
