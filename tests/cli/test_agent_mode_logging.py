"""run_start carries agent_mode bool field (spec §4.5)."""

from __future__ import annotations

import json
import logging

import pytest


@pytest.fixture(autouse=True)
def _teardown_logging():
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)


def _stub_aa_pipeline(monkeypatch):
    """Make --list-reportsuites runnable without network."""
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.models import ReportSuiteSummary
    from aa_auto_sdr.core import credentials
    from aa_auto_sdr.core.credentials import Credentials

    monkeypatch.setattr(
        credentials,
        "resolve",
        lambda profile=None: Credentials(  # noqa: ARG005
            org_id="x",
            client_id="y",
            secret="z",
            scopes="openid,AdobeID,additional_info.projectedProductContext",
            source="test",
        ),
    )
    monkeypatch.setattr(AaClient, "from_credentials", classmethod(lambda cls, creds, **kwargs: object()))  # noqa: ARG005
    monkeypatch.setattr(
        fetch,
        "fetch_report_suite_summaries",
        lambda client: [ReportSuiteSummary(rsid="RS1", name="Suite 1")],  # noqa: ARG005
    )


def test_run_start_records_agent_mode_true(tmp_path, monkeypatch):
    """When --agent-mode is set, run_start record carries agent_mode=True."""
    monkeypatch.chdir(tmp_path)
    _stub_aa_pipeline(monkeypatch)

    from aa_auto_sdr.cli.main import run

    run(["--list-reportsuites", "--agent-mode"])

    log_files = sorted((tmp_path / "logs").glob("*.log"))
    assert log_files, "no log file written"
    lines = log_files[-1].read_text().splitlines()
    run_start_lines = [json.loads(line) for line in lines if "run_start" in line]
    assert run_start_lines, "run_start log record missing"
    assert run_start_lines[0].get("agent_mode") is True


def test_run_start_records_agent_mode_false_by_default(tmp_path, monkeypatch):
    """When --agent-mode is not set, run_start record carries agent_mode=False."""
    monkeypatch.chdir(tmp_path)
    _stub_aa_pipeline(monkeypatch)

    from aa_auto_sdr.cli.main import run

    run(["--list-reportsuites", "--log-format", "json"])

    log_files = sorted((tmp_path / "logs").glob("*.log"))
    assert log_files, "no log file written"
    lines = log_files[-1].read_text().splitlines()
    run_start_lines = [json.loads(line) for line in lines if "run_start" in line]
    assert run_start_lines, "run_start log record missing"
    assert run_start_lines[0].get("agent_mode") is False


def test_run_start_ndjson_includes_agent_mode(tmp_path, monkeypatch):
    """JSON-mode run_start NDJSON file carries agent_mode field."""
    monkeypatch.chdir(tmp_path)
    _stub_aa_pipeline(monkeypatch)

    from aa_auto_sdr.cli.main import run

    run(["--list-reportsuites", "--agent-mode"])

    log_files = sorted((tmp_path / "logs").glob("*.log"))
    assert log_files, "no log file written"
    lines = log_files[-1].read_text().splitlines()
    run_start_lines = [json.loads(line) for line in lines if "run_start" in line]
    assert run_start_lines
    assert run_start_lines[0].get("agent_mode") is True


def test_run_complete_records_agent_mode(tmp_path, monkeypatch):
    """run_complete record also carries agent_mode for log-aggregation queries."""
    monkeypatch.chdir(tmp_path)
    _stub_aa_pipeline(monkeypatch)

    from aa_auto_sdr.cli.main import run

    run(["--list-reportsuites", "--agent-mode"])

    log_files = sorted((tmp_path / "logs").glob("*.log"))
    assert log_files, "no log file written"
    lines = log_files[-1].read_text().splitlines()
    run_complete_lines = [json.loads(line) for line in lines if "run_complete" in line]
    assert run_complete_lines, "run_complete log record missing"
    assert run_complete_lines[0].get("agent_mode") is True


def test_agent_mode_stdout_suppresses_info_on_console(tmp_path, monkeypatch, capsys):
    """Codex review (P2): ``--list-reportsuites --agent-mode`` routes to stdout,
    so the documented ``--output -`` ⇒ ``--quiet`` contract must silence INFO
    records on stderr. Errors and the final result still print, but progress /
    startup chatter does not."""
    monkeypatch.chdir(tmp_path)
    _stub_aa_pipeline(monkeypatch)

    from aa_auto_sdr.cli.main import run

    run(["--list-reportsuites", "--agent-mode"])
    captured = capsys.readouterr()

    # The JSON payload still lands on stdout.
    assert '"rsid"' in captured.out
    # INFO chatter — run_start, command_start, run_complete — must NOT appear on stderr.
    assert "run_start" not in captured.err
    assert "command_start" not in captured.err
    assert "run_complete" not in captured.err
    # The log file is unaffected — records are still captured for triage.
    log_files = sorted((tmp_path / "logs").glob("*.log"))
    assert log_files, "no log file written"
    log_text = log_files[-1].read_text()
    assert "run_start" in log_text
    assert "run_complete" in log_text


def test_explicit_output_dash_also_implies_quiet(tmp_path, monkeypatch, capsys):
    """The same contract applies to explicit ``--output -`` (no agent-mode):
    INFO console output is suppressed because the user is reading stdout."""
    monkeypatch.chdir(tmp_path)
    _stub_aa_pipeline(monkeypatch)

    from aa_auto_sdr.cli.main import run

    run(["--list-reportsuites", "--format", "json", "--output", "-", "--log-format", "json"])
    captured = capsys.readouterr()

    assert '"rsid"' in captured.out
    assert "run_start" not in captured.err
    assert "run_complete" not in captured.err
