"""v1.4 — assert that cli/main.run emits the documented lifecycle events
with the documented extras. Test discipline: assert event-prefix substring
+ level + extras presence, never full message wording (see spec §8).

Implementation note on log capture: ``setup_logging`` strips root handlers
when it (re)installs its console + file pair, which removes pytest's
default caplog handler. To survive that, we attach ``caplog.handler``
directly to the ``aa_auto_sdr`` package logger before calling ``run()`` —
records propagate up to it before reaching root, so they reach caplog
regardless of what setup_logging does to the root handler list."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from aa_auto_sdr.cli.main import run


def _records_with_event(caplog, event: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if event in r.getMessage()]


def _attach_caplog_to_package_logger(caplog) -> None:
    """Attach caplog's handler to the aa_auto_sdr package logger so it
    survives setup_logging's root-handler reset."""
    pkg = logging.getLogger("aa_auto_sdr")
    pkg.addHandler(caplog.handler)
    pkg.setLevel(logging.DEBUG)


def test_run_emits_run_start_with_run_mode_and_argv_summary(caplog, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.INFO)
    _attach_caplog_to_package_logger(caplog)
    # --show-config is a no-auth path; deterministic exit, no Adobe call.
    run(["--show-config"])
    starts = _records_with_event(caplog, "run_start")
    assert len(starts) == 1
    rec = starts[0]
    assert rec.levelno == logging.INFO
    assert rec.run_mode == "config"
    # argv_summary contains flag names only, never positional values.
    assert isinstance(rec.argv_summary, list)
    assert "--show-config" in rec.argv_summary


def test_run_emits_run_complete_with_exit_code_and_duration_ms(caplog, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.INFO)
    _attach_caplog_to_package_logger(caplog)
    run(["--show-config"])
    completes = _records_with_event(caplog, "run_complete")
    assert len(completes) == 1
    rec = completes[0]
    assert rec.levelno == logging.INFO
    assert isinstance(rec.exit_code, int)
    assert isinstance(rec.duration_ms, int)
    assert rec.duration_ms >= 0


def test_run_emits_run_failure_on_exception(caplog, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.ERROR)
    _attach_caplog_to_package_logger(caplog)
    # Force the dispatch helper to raise.
    with (
        patch("aa_auto_sdr.cli.main._dispatch", side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError),
    ):
        run(["--show-config"])
    failures = _records_with_event(caplog, "run_failure")
    assert len(failures) == 1
    rec = failures[0]
    assert rec.levelno == logging.ERROR
    assert rec.error_class == "RuntimeError"
    assert isinstance(rec.exit_code, int)


def test_fast_path_commands_emit_no_records(caplog, tmp_path, monkeypatch):
    """Spec §6.5 silent-fast-path contract: --version/--help/--exit-codes/
    --explain-exit-code/--completion skip setup_logging entirely, so they
    must NOT produce any log records. Asserted via __main__.main()."""
    from aa_auto_sdr.__main__ import main

    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.DEBUG)
    _attach_caplog_to_package_logger(caplog)
    main(["--version"])
    main(["--help"])
    main(["--exit-codes"])
    assert caplog.records == []
