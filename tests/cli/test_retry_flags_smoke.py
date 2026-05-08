"""End-to-end (mocked SDK): retry flags reach the fetcher layer; --agent-mode composes.

These smoke tests exercise the real CLI through `cli.main.run`, with patches at
the `aanalytics2` SDK boundary inside `api/client.py` (so the real
`AaClient.from_credentials` bootstrap and the real `with_retries` /
`_classify_transient_sdk_call` plumbing run end-to-end). Verifies:

1. `--max-retries N` actually drives the fetcher's retry budget — N+1 SDK
   call attempts on transient failure.
2. Retry exhaustion bubbles cleanly to ApiError → ExitCode.API (12).
3. `--agent-mode` and retry flags compose orthogonally.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from aa_auto_sdr.cli.main import run
from aa_auto_sdr.core.credentials import Credentials
from aa_auto_sdr.core.exit_codes import ExitCode


@pytest.fixture(autouse=True)
def _teardown_logging():
    """Mirror test_agent_mode_smoke.py — strip any handlers attached during run()."""
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)


@pytest.fixture
def mock_aa(monkeypatch: pytest.MonkeyPatch):
    """Patches aanalytics2 calls + credential resolution to simulate a real run.

    Returns the mocked Analytics handle so tests configure `.getReportSuites`
    side effects directly. The real `AaClient.from_credentials` bootstrap runs
    against this handle, so retry plumbing in the fetcher layer is exercised
    end-to-end."""
    # Skip backoff sleeps — keeps the tests fast and deterministic.
    monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)

    handle = MagicMock()
    login_instance = MagicMock()
    login_instance.getCompanyId.return_value = [{"globalCompanyId": "co"}]

    # Patch the aanalytics2 entry points used by AaClient.from_credentials.
    # These are accessed as `aanalytics2.<name>` after `import aanalytics2`.
    patches = [
        patch("aa_auto_sdr.api.client.aanalytics2.configure"),
        patch("aa_auto_sdr.api.client.aanalytics2.Login", return_value=login_instance),
        patch("aa_auto_sdr.api.client.aanalytics2.Analytics", return_value=handle),
    ]
    for p in patches:
        p.start()

    fake_creds = Credentials(
        org_id="org@AdobeOrg",
        client_id="abcdef0123",
        secret="s3cret",
        scopes="openid,AdobeID,additional_info.projectedProductContext",
        source="test",
    )
    # Patch the lookup `discovery.py` performs: `from aa_auto_sdr.core import credentials`
    # then `credentials.resolve(profile=...)`. Patching the function on the module
    # object covers every importer that goes through the same module reference.
    monkeypatch.setattr(
        "aa_auto_sdr.core.credentials.resolve",
        lambda profile=None: fake_creds,  # noqa: ARG005
    )

    yield handle

    for p in patches:
        p.stop()


def test_max_retries_5_with_4_failures_then_success(mock_aa, capsys) -> None:
    """SDK fails 4 times then succeeds — exit 0; retry budget honored."""
    mock_aa.getReportSuites.side_effect = [
        KeyError("content"),
        KeyError("content"),
        KeyError("content"),
        KeyError("content"),
        pd.DataFrame([{"rsid": "rs1", "name": "RS One"}]),
    ]
    rc = run(["--list-reportsuites", "--max-retries", "5", "--format", "json"])
    capsys.readouterr()  # consume any stdout/stderr
    assert rc == ExitCode.OK.value
    assert mock_aa.getReportSuites.call_count == 5


def test_max_retries_2_exhausts_to_api_error(mock_aa, capsys) -> None:
    """SDK fails on every attempt; --max-retries 2 → 3 attempts → exit 12.

    KeyError is translated to TransientApiError by _classify_transient_sdk_call,
    retried per the budget, then the underlying TransientApiError (subclass of
    ApiError) bubbles after exhaustion. The CLI's `except ApiError` catch in
    discovery.run_list_reportsuites translates it to ExitCode.API."""
    mock_aa.getReportSuites.side_effect = KeyError("content")
    rc = run(["--list-reportsuites", "--max-retries", "2"])
    capsys.readouterr()
    assert rc == ExitCode.API.value
    assert mock_aa.getReportSuites.call_count == 3  # 1 initial + 2 retries


def test_agent_mode_composes_with_retry_flags(mock_aa, tmp_path, monkeypatch, capsys) -> None:
    """`--agent-mode` sets json/stdout/json-log defaults; `--max-retries 6` is preserved.

    Confirms the agent-mode preset and retry-policy resolution are orthogonal:
    neither overrides the other. Single SDK call, no failures — we're checking
    that argv composition doesn't drop or mangle the retry flags."""
    monkeypatch.chdir(tmp_path)
    mock_aa.getReportSuites.return_value = pd.DataFrame([{"rsid": "rs1", "name": "RS One"}])
    rc = run(["--list-reportsuites", "--agent-mode", "--max-retries", "6"])
    capsys.readouterr()
    assert rc == ExitCode.OK.value
    # No transient failures → exactly one SDK call. The point is composition,
    # not retry count.
    assert mock_aa.getReportSuites.call_count == 1
