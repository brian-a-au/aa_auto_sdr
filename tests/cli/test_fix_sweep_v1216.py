"""v1.21.6 fix-sweep regression tests.

Covers: errors-to-stderr (cja parity), --version position independence, the
diff error envelope on implicit stdout, the generate pipe-path quality gate,
pipe-path snapshot-save errors, dry-run preview names, batch dry-run exit
codes, git/template validator scope, and resolution-chain accuracy.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.cli.commands import batch as batch_cmd
from aa_auto_sdr.cli.commands import diff as diff_cmd
from aa_auto_sdr.cli.commands import generate as generate_cmd
from aa_auto_sdr.cli.main import (
    _validate_git_modifiers,
    _validate_template_modifiers,
    run,
)
from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import OutputError
from aa_auto_sdr.sdr.document import SdrDocument

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


@pytest.fixture(autouse=True)
def _teardown_logging():
    """run() wires real console handlers via setup_logging; strip them so log
    records don't leak onto later tests' captured stderr."""
    import logging

    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)


def _envelope_from(stderr: str) -> dict:
    """Extract the JSON error envelope from stderr, tolerating log lines
    around it (setup_logging from earlier tests wires a console handler)."""
    for raw_line in stderr.splitlines():
        line = raw_line.strip()
        if line.startswith("{"):
            parsed = json.loads(line)
            if "error" in parsed:
                return parsed
    raise AssertionError(f"no JSON error envelope found on stderr: {stderr!r}")


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


def _build_handle() -> MagicMock:
    import pandas as pd

    raw = json.loads(FIXTURE.read_text())

    def _df(records: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(records)

    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    return handle


def _fake_doc(*, verdict: str | None = None) -> SdrDocument:
    rs = models.ReportSuite(rsid="demo.prod", name="Demo", timezone=None, currency=None, parent_rsid=None)
    doc = SdrDocument(
        report_suite=rs,
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 7, 11, tzinfo=UTC),
        tool_version="1.21.6",
    )
    if verdict is not None:
        doc = dataclasses.replace(
            doc,
            quality={
                "naming_audit": {},
                "stale_components": [],
                "issues": [],
                "summary": {"by_severity": {}, "total": 1, "verdict": verdict},
            },
        )
    return doc


# --- errors go to stderr (cja parity) ---------------------------------------


class TestErrorsGoToStderr:
    def test_batch_output_stdout_rejection(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = run(["--batch", "rsA", "rsB", "--output", "-"])
        assert rc == 15
        captured = capsys.readouterr()
        assert "ambiguous" in captured.err
        assert "error" not in captured.out

    def test_diff_with_positional_rsids_rejection(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = run(["--diff", "a.json", "b.json", "rsX"])
        assert rc == 2
        captured = capsys.readouterr()
        assert "cannot be combined" in captured.err
        assert "error" not in captured.out

    def test_fastpath_explain_exit_code_missing_arg(self, capsys: pytest.CaptureFixture[str]) -> None:
        from aa_auto_sdr.__main__ import main

        rc = main(["--explain-exit-code"])
        assert rc == 2
        captured = capsys.readouterr()
        assert "requires a CODE argument" in captured.err
        assert captured.out == ""


# --- --version works in any argv position ------------------------------------


class TestVersionFlagRegistered:
    def test_version_after_other_flags(self, capsys: pytest.CaptureFixture[str]) -> None:
        from aa_auto_sdr.__main__ import main

        with pytest.raises(SystemExit) as excinfo:
            main(["--quiet", "--version"])
        assert excinfo.value.code == 0
        assert "aa_auto_sdr" in capsys.readouterr().out


# --- diff: implicit stdout gets the JSON error envelope ----------------------


class TestDiffImplicitStdoutEnvelope:
    def test_json_format_without_output_flag(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        rc = diff_cmd.run(
            a=str(tmp_path / "missing_a.json"),
            b=str(tmp_path / "missing_b.json"),
            format_name="json",
            output=None,
            profile=None,
        )
        assert rc == 16
        captured = capsys.readouterr()
        assert captured.out == ""
        envelope = _envelope_from(captured.err)
        assert envelope["error"]["code"] == 16


# --- generate pipe path: quality gate + quality report + save errors ---------


class TestGeneratePipePath:
    @patch("aa_auto_sdr.cli.commands.generate.AaClient")
    def test_quality_gate_fires_on_pipe_path(
        self, mock_client_cls, env_creds, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(), company_id="testco")
        monkeypatch.setattr(generate_cmd, "build_sdr", lambda *_a, **_k: _fake_doc(verdict="fail"))
        rc = generate_cmd.run(
            rsid="demo.prod",
            output_dir=Path("-"),
            format_name="json",
            profile=None,
            fail_on_quality="LOW",
            audit_naming=True,
        )
        assert rc == 17
        out = capsys.readouterr().out
        assert json.loads(out)["report_suite"]["rsid"] == "demo.prod"  # payload still emitted

    @patch("aa_auto_sdr.cli.commands.generate.AaClient")
    def test_quality_report_rejected_on_pipe_path(self, mock_client_cls, env_creds, capsys) -> None:
        mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(), company_id="testco")
        rc = generate_cmd.run(
            rsid="demo.prod",
            output_dir=Path("-"),
            format_name="json",
            profile=None,
            quality_report="json",
            audit_naming=True,
        )
        assert rc == 15
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "quality-report" in captured.err

    @patch("aa_auto_sdr.cli.commands.generate.AaClient")
    def test_snapshot_save_failure_returns_output_error(
        self, mock_client_cls, env_creds, monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path
    ) -> None:
        mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(), company_id="testco")
        monkeypatch.setattr(generate_cmd, "build_sdr", lambda *_a, **_k: _fake_doc())

        def explode(*a, **k):
            raise OutputError("snapshot write failed at /nowhere: disk full")

        import aa_auto_sdr.snapshot.store as store_mod

        monkeypatch.setattr(store_mod, "save_snapshot", explode)
        rc = generate_cmd.run(
            rsid="demo.prod",
            output_dir=Path("-"),
            format_name="json",
            profile=None,
            snapshot=True,
            snapshot_dir=tmp_path,
        )
        assert rc == 15
        envelope = _envelope_from(capsys.readouterr().err)
        assert envelope["error"]["type"] == "OutputError"


# --- dry-run preview names ----------------------------------------------------


class TestDryRunPreviewNames:
    @patch("aa_auto_sdr.cli.commands.generate.AaClient")
    def test_template_preview_uses_xlsx_extension(self, mock_client_cls, env_creds, capsys, tmp_path: Path) -> None:
        mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(), company_id="testco")
        template = tmp_path / "t.xlsx"
        template.write_bytes(b"")
        rc = generate_cmd.run(
            rsid="demo.prod",
            output_dir=tmp_path,
            format_name="excel",
            profile=None,
            dry_run=True,
            template_path=template,
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "demo.prod.xlsx" in out
        assert "demo.prod.excel-template" not in out

    @patch("aa_auto_sdr.cli.commands.batch.AaClient")
    def test_batch_notion_preview_names_registry(self, mock_client_cls, env_creds, capsys, tmp_path: Path) -> None:
        from aa_auto_sdr.output.notion_registry import REGISTRY_FILENAME

        mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(), company_id="testco")
        rc = batch_cmd.run(
            rsids=["demo.prod"],
            output_dir=tmp_path,
            format_name="notion",
            profile=None,
            dry_run=True,
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert REGISTRY_FILENAME in out
        assert "demo.prod.notion" not in out


# --- batch dry-run exit codes --------------------------------------------------


class TestBatchDryRunExitCodes:
    @patch("aa_auto_sdr.cli.commands.batch.AaClient")
    def test_partial_when_some_identifiers_unresolvable(
        self, mock_client_cls, env_creds, capsys, tmp_path: Path
    ) -> None:
        mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(), company_id="testco")
        rc = batch_cmd.run(
            rsids=["demo.prod", "ghost.rsid"],
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            dry_run=True,
        )
        assert rc == 14

    @patch("aa_auto_sdr.cli.commands.batch.AaClient")
    def test_failure_code_when_all_identifiers_unresolvable(
        self, mock_client_cls, env_creds, capsys, tmp_path: Path
    ) -> None:
        mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(), company_id="testco")
        rc = batch_cmd.run(
            rsids=["ghost.rsid"],
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            dry_run=True,
        )
        assert rc == 13


# --- git/template validators reject snapshot-lifecycle/profile/config modes ----


class TestModifierValidatorScope:
    def test_git_commit_rejected_with_list_snapshots(self, capsys) -> None:
        ns = argparse.Namespace(git_commit=True, git_push=False, git_message=None, list_snapshots=True)
        assert _validate_git_modifiers(ns) == 2
        assert "SDR-generating action" in capsys.readouterr().err

    def test_git_commit_rejected_with_profile_list(self, capsys) -> None:
        ns = argparse.Namespace(git_commit=True, git_push=False, git_message=None, profile_list=True)
        assert _validate_git_modifiers(ns) == 2

    def test_template_rejected_with_prune_snapshots(self, capsys, tmp_path: Path) -> None:
        template = tmp_path / "t.xlsx"
        template.write_bytes(b"")
        ns = argparse.Namespace(template=template, template_organization=None, prune_snapshots=True)
        assert _validate_template_modifiers(ns) == 2
        assert "SDR-generating action" in capsys.readouterr().err


# --- resolution chain reflects real resolution behavior ------------------------


class TestResolutionChainAccuracy:
    def test_incomplete_profile_never_matches(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """An existing-but-incomplete profile cannot resolve; the chain must not
        report it as matched — and no later source matches either, because an
        explicit profile halts resolution (resolve() raises, no fallback)."""
        prof_dir = tmp_path / "orgs" / "broken"
        prof_dir.mkdir(parents=True)
        (prof_dir / "config.json").write_text('{"org_id": "O@AdobeOrg"}')
        for var, val in (("ORG_ID", "O"), ("CLIENT_ID", "C"), ("SECRET", "S"), ("SCOPES", "X")):
            monkeypatch.setenv(var, val)
        chain = credentials.resolution_chain(
            profile="broken",
            profiles_base=tmp_path,
            working_dir=tmp_path,
        )
        assert chain[0].matched is False
        assert all(entry.matched is False for entry in chain)

    def test_complete_profile_matches(self, tmp_path: Path) -> None:
        prof_dir = tmp_path / "orgs" / "good"
        prof_dir.mkdir(parents=True)
        (prof_dir / "config.json").write_text(
            '{"org_id": "O@AdobeOrg", "client_id": "C", "secret": "S", "scopes": "X"}'
        )
        chain = credentials.resolution_chain(
            profile="good",
            profiles_base=tmp_path,
            working_dir=tmp_path,
        )
        assert chain[0].matched is True


# --- Codex review round 1 -------------------------------------------------


def _build_multi_handle(rsids: list[str]) -> MagicMock:
    """A handle whose getReportSuites resolves every rsid in `rsids`, so all of
    them reach run_batch rather than failing to resolve as pre_failures."""
    import pandas as pd

    raw = json.loads(FIXTURE.read_text())
    base = raw["report_suite"]
    records = [{**base, "rsid": r, "name": r} for r in rsids]
    handle = MagicMock()
    handle.getReportSuites.return_value = pd.DataFrame(records)
    handle.getDimensions.return_value = pd.DataFrame(raw["dimensions"])
    handle.getMetrics.return_value = pd.DataFrame(raw["metrics"])
    handle.getSegments.return_value = pd.DataFrame(raw["segments"])
    handle.getCalculatedMetrics.return_value = pd.DataFrame(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = pd.DataFrame(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = pd.DataFrame(raw["classification_datasets"])
    return handle


class TestFailFastExitCodePreserved:
    @patch("aa_auto_sdr.cli.commands.batch.AaClient")
    def test_sequential_all_failed_keeps_triggering_code(
        self, mock_client_cls, env_creds, monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path
    ) -> None:
        """Fail-fast appends synthetic cancellations after the real failure. With
        multiple RSIDs and all-failed, the exit code must stay the triggering
        error's code (API=12), not the trailing cancellation's GENERIC (1)."""
        from aa_auto_sdr.core.exceptions import ApiError
        from aa_auto_sdr.pipeline import batch as batch_runner_mod

        mock_client_cls.from_credentials.return_value = MagicMock(
            handle=_build_multi_handle(["a.rs", "b.rs", "c.rs"]), company_id="testco"
        )

        def boom(**_kw):
            raise ApiError("rate limit exceeded")

        monkeypatch.setattr(batch_runner_mod, "run_single", boom)
        rc = batch_cmd.run(
            rsids=["a.rs", "b.rs", "c.rs"],
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            workers=1,
            fail_fast=True,
        )
        assert rc == 12


class TestModifierValidatorDiagnosticActions:
    def test_git_commit_rejected_with_exit_codes(self, capsys) -> None:
        ns = argparse.Namespace(git_commit=True, git_push=False, git_message=None, exit_codes=True)
        assert _validate_git_modifiers(ns) == 2

    def test_git_commit_rejected_with_explain_exit_code_zero(self, capsys) -> None:
        """explain_exit_code=0 is falsy but a legitimate request; must still trip."""
        ns = argparse.Namespace(git_commit=True, git_push=False, git_message=None, explain_exit_code=0)
        assert _validate_git_modifiers(ns) == 2

    def test_template_rejected_with_completion(self, capsys, tmp_path: Path) -> None:
        template = tmp_path / "t.xlsx"
        template.write_bytes(b"")
        ns = argparse.Namespace(template=template, template_organization=None, completion="bash")
        assert _validate_template_modifiers(ns) == 2


# --- Codex review round 4 --------------------------------------------------


class TestPipeReportConflictBeforeCreds:
    def test_quality_report_pipe_conflict_wins_over_missing_creds(
        self, monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path
    ) -> None:
        """--output - + --quality-report is a pure argument conflict (exit 15);
        it must be reported before the credential round-trip, so a missing-creds
        environment does not mask it with CONFIG (10)."""
        for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
            monkeypatch.delenv(v, raising=False)
        monkeypatch.chdir(tmp_path)  # no config.json to pick up
        rc = generate_cmd.run(
            rsid="demo.prod",
            output_dir=Path("-"),
            format_name="json",
            profile=None,
            quality_report="json",
            audit_naming=True,
        )
        assert rc == 15
        assert "quality-report" in capsys.readouterr().err


class TestFailFastResolutionPhase:
    @patch("aa_auto_sdr.cli.commands.batch.AaClient")
    def test_fail_fast_halts_on_first_resolution_failure(
        self, mock_client_cls, env_creds, capsys, tmp_path: Path
    ) -> None:
        """Under --fail-fast, a resolution failure at the first identifier stops
        the batch: later identifiers are cancelled and never generate."""
        mock_client_cls.from_credentials.return_value = MagicMock(
            handle=_build_multi_handle(["valid"]), company_id="testco"
        )
        rc = batch_cmd.run(
            rsids=["missing", "valid"],
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            workers=1,
            fail_fast=True,
        )
        assert rc == 13  # all failed → NOT_FOUND (the triggering resolution error)
        assert not (tmp_path / "valid.json").exists()  # valid never generated

    @patch("aa_auto_sdr.cli.commands.batch.AaClient")
    def test_fail_fast_keeps_successes_before_the_failure(
        self, mock_client_cls, env_creds, capsys, tmp_path: Path
    ) -> None:
        """An identifier that resolved before the failing one still generates."""
        mock_client_cls.from_credentials.return_value = MagicMock(
            handle=_build_multi_handle(["valid"]), company_id="testco"
        )
        rc = batch_cmd.run(
            rsids=["valid", "missing"],
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            workers=1,
            fail_fast=True,
        )
        assert rc == 14  # partial: valid succeeded, missing failed
        assert (tmp_path / "valid.json").exists()

    @patch("aa_auto_sdr.cli.commands.batch.AaClient")
    def test_without_fail_fast_reports_all_resolution_failures(
        self, mock_client_cls, env_creds, capsys, tmp_path: Path
    ) -> None:
        """Continue-on-error still reports every bad identifier and generates the
        good ones — the report-all-typos behavior is preserved without fail-fast."""
        mock_client_cls.from_credentials.return_value = MagicMock(
            handle=_build_multi_handle(["valid"]), company_id="testco"
        )
        rc = batch_cmd.run(
            rsids=["missing1", "valid", "missing2"],
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            workers=1,
            fail_fast=False,
        )
        assert rc == 14
        assert (tmp_path / "valid.json").exists()
        err = capsys.readouterr().err
        assert "missing1" in err
        assert "missing2" in err


class TestFailFastResolutionDuplicateGuard:
    @patch("aa_auto_sdr.cli.commands.batch.AaClient")
    def test_duplicate_after_failure_not_double_counted(
        self, mock_client_cls, env_creds, capsys, tmp_path: Path
    ) -> None:
        """`valid missing valid --fail-fast`: the trailing duplicate that already
        resolved must not be recorded as cancelled on top of its success — it
        stays a single success, not both a success and a cancelled failure."""
        mock_client_cls.from_credentials.return_value = MagicMock(
            handle=_build_multi_handle(["valid"]), company_id="testco"
        )
        rc = batch_cmd.run(
            rsids=["valid", "missing", "valid"],
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            workers=1,
            fail_fast=True,
        )
        assert rc == 14  # partial: valid succeeded, missing failed
        out = capsys.readouterr().out
        # The guard prevents the trailing duplicate from being recorded as a
        # cancellation; with no other cancellations in this run, none appear.
        assert "CancelledError" not in out
        assert (tmp_path / "valid.json").exists()
