"""v1.2.1 batch: --show-timings wiring (covers post-auth error-path emit branches)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aa_auto_sdr.cli.commands import batch as cmd
from aa_auto_sdr.core import timings
from aa_auto_sdr.core.exit_codes import ExitCode


@pytest.fixture(autouse=True)
def _reset_timings() -> None:
    timings.disable()
    timings.clear()
    yield
    timings.disable()
    timings.clear()


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_show_timings_emits_block_on_auth_error(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When batch auth fails AND --show-timings is set, the timings block emits."""
    from aa_auto_sdr.core.exceptions import AuthError

    mock_client_cls.from_credentials.side_effect = AuthError("bad creds")
    rc = cmd.run(
        rsids=["demo.prod"],
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        show_timings=True,
    )
    assert rc == ExitCode.AUTH.value
    err = capsys.readouterr().err
    assert "Timings:" in err
    assert "auth" in err  # the Timer("auth") row should appear even on AuthError
