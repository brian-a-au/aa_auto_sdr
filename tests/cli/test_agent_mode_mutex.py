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


def _forbid_credentials(monkeypatch):
    from aa_auto_sdr.core import credentials

    def _boom(*_a, **_k):
        raise AssertionError("credentials must not be resolved")

    monkeypatch.setattr(credentials, "resolve", _boom)


@pytest.mark.parametrize(
    "argv",
    [
        ["RS1", "--dry-run", "--output", "-"],
        ["RS1", "--dry-run", "--agent-mode", "--output", "-"],
    ],
)
def test_dry_run_with_stdout_output_rejected(argv, tmp_path, monkeypatch, capsys):
    """--dry-run prints a text preview, which cannot share stdout with the JSON payload."""
    monkeypatch.chdir(tmp_path)
    _forbid_credentials(monkeypatch)
    from aa_auto_sdr.cli.main import run

    exit_code = run(argv)
    out, err = capsys.readouterr()
    assert exit_code == ExitCode.USAGE.value
    assert out == ""
    assert "--dry-run" in err
    assert "--output -" in err


def test_dry_run_agent_mode_excel_still_previews(tmp_path, monkeypatch):
    """Agent-mode with a file-only format writes files, so the preview stays allowed."""
    monkeypatch.chdir(tmp_path)
    from aa_auto_sdr.cli.commands import generate

    calls = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return 0

    monkeypatch.setattr(generate, "run", fake_run)
    from aa_auto_sdr.cli.main import run

    assert run(["RS1", "--agent-mode", "--format", "excel", "--dry-run"]) == 0
    assert calls
    assert calls[0]["dry_run"] is True
