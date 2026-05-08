"""Mutex: --agent-mode + explicit --run-summary-json - exits OUTPUT(15) (spec §4.3)."""

from __future__ import annotations

import logging

import pytest

from aa_auto_sdr.core.exit_codes import ExitCode


@pytest.fixture(autouse=True)
def _teardown_logging():
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)


def test_agent_mode_plus_run_summary_stdout_exits_output(tmp_path, monkeypatch):
    """Agent-mode sets implicit --output -; explicit --run-summary-json - clashes ⇒ exit 15."""
    monkeypatch.chdir(tmp_path)
    from aa_auto_sdr.cli.main import run

    exit_code = run(["RS1", "--agent-mode", "--run-summary-json", "-"])
    assert exit_code == ExitCode.OUTPUT.value


def test_agent_mode_plus_run_summary_file_does_not_clash(tmp_path, monkeypatch):
    """Run-summary to file path is fine even with agent-mode's --output -."""
    monkeypatch.chdir(tmp_path)
    from aa_auto_sdr.cli.main import run

    # Stub credentials so we don't actually hit the API
    from aa_auto_sdr.core import credentials
    from aa_auto_sdr.core.exceptions import ConfigError

    def fail_resolve(profile=None):
        raise ConfigError("stub: no creds")

    monkeypatch.setattr(credentials, "resolve", fail_resolve)

    out = tmp_path / "summary.json"
    exit_code = run(["RS1", "--agent-mode", "--run-summary-json", str(out)])
    # Exits CONFIG (10) due to stub, not OUTPUT (15).
    assert exit_code == ExitCode.CONFIG.value
