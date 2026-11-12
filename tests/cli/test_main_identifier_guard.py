"""A report-suite identifier that starts with `--` is a flag passed as one token.

`aa_auto_sdr "--completion bash"` reaches argparse as one token with a space
in it, so argparse reads it as a positional report-suite name. Before the
guard, the tool then resolved credentials, signed in, and looked the name up
(exit 13). The guard rejects any identifier that starts with two hyphens with
exit 2 before credential resolution. A single leading hyphen stays accepted,
because a real report-suite name can start with one.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest

from aa_auto_sdr.__main__ import main

_GUARD_TEXT = "looks like a flag"


@pytest.fixture
def resolve_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[tuple]:
    """Run in an empty temp dir with no credentials. Credential resolution
    records the call and raises AssertionError, so a test that reaches it
    fails loudly instead of signing in."""
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    calls: list[tuple] = []

    def _resolve(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("credentials.resolve was reached")

    monkeypatch.setattr("aa_auto_sdr.core.credentials.resolve", _resolve)
    return calls


_REJECTED = [
    pytest.param(["--completion bash"], "--completion bash", id="single-positional-completion"),
    pytest.param(["--explain-exit-code 12"], "--explain-exit-code 12", id="single-positional-explain"),
    pytest.param(["rs1", "--format json"], "--format json", id="auto-batch-positional"),
    pytest.param(["--batch", "--list-metrics rs1", "rs2"], "--list-metrics rs1", id="batch-value"),
    pytest.param(["--", "--rs1"], "--rs1", id="after-end-of-options"),
    pytest.param(["--describe-reportsuite", "--a b"], "--a b", id="describe-reportsuite"),
    pytest.param(["--list-metrics=--rs1"], "--rs1", id="list-metrics"),
    pytest.param(["--list-dimensions", "--a b"], "--a b", id="list-dimensions"),
    pytest.param(["--list-segments=--rs1"], "--rs1", id="list-segments"),
    pytest.param(["--list-calculated-metrics", "--a b"], "--a b", id="list-calculated-metrics"),
    pytest.param(["--list-classification-datasets=--rs1"], "--rs1", id="list-classification-datasets"),
    pytest.param(["--stats", "--a b"], "--a b", id="stats"),
    pytest.param(["--inventory-summary", "--a b"], "--a b", id="inventory-summary"),
    pytest.param(["--a b", "--trending-window", "7d", "--snapshot-dir", "snaps"], "--a b", id="trending-window"),
    pytest.param(["--a b", "--compare-with-prev", "--snapshot-dir", "snaps"], "--a b", id="compare-with-prev"),
    pytest.param(["--a b", "--watch", "--interval", "1h"], "--a b", id="watch"),
    pytest.param(["--list-snapshots", "--snapshot-dir", "snaps", "--a b"], "--a b", id="list-snapshots"),
]


@pytest.mark.parametrize(("argv", "bad"), _REJECTED)
def test_double_hyphen_identifier_is_rejected_before_credentials(
    argv: list[str],
    bad: str,
    resolve_calls: list[tuple],
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(list(argv))
    captured = capsys.readouterr()
    assert rc == 2
    assert resolve_calls == []
    assert f"error: identifier '{bad}' looks like a flag" in captured.err
    assert "quote" in captured.err
    assert captured.out == ""


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["--agent-mode", "--completion bash"], id="agent-mode"),
        pytest.param(["--output", "-", "--list-metrics", "--a b"], id="output-dash"),
    ],
)
def test_pipe_path_emits_json_error_envelope(
    argv: list[str],
    resolve_calls: list[tuple],
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(list(argv))
    captured = capsys.readouterr()
    assert rc == 2
    assert resolve_calls == []
    assert captured.out == ""
    lines = [ln for ln in captured.err.splitlines() if ln.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["error"]["code"] == 2
    assert _GUARD_TEXT in payload["error"]["message"]


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["rs1"], id="plain-rsid"),
        # argparse rejects a bare `-dash-name` as an unknown option, so a
        # single-hyphen name reaches the guard with a space or after `--`.
        pytest.param(["-dash name"], id="single-hyphen-with-space"),
        pytest.param(["--", "-dash-name"], id="single-hyphen-after-end-of-options"),
        pytest.param(["--list-metrics=-dash-name"], id="single-hyphen-inline"),
        pytest.param(["--batch", "-dash name", "rs2"], id="single-hyphen-batch"),
        # Non-identifier flag values that start with `--` are not checked.
        pytest.param(["--list-metrics", "rs1", "--filter=--x"], id="filter-value"),
    ],
)
def test_accepted_identifier_reaches_credentials(
    argv: list[str],
    resolve_calls: list[tuple],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with contextlib.suppress(AssertionError):
        main(list(argv))
    assert resolve_calls, "expected the run to reach credentials.resolve"
    assert _GUARD_TEXT not in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["--diff", "--a b", "--c d"], id="diff-tokens"),
        pytest.param(["--render-from", "--a b"], id="render-from-token"),
    ],
)
def test_guard_ignores_non_identifier_tokens(
    argv: list[str],
    resolve_calls: list[tuple],
    capsys: pytest.CaptureFixture[str],
) -> None:
    with contextlib.suppress(AssertionError):
        main(list(argv))
    assert _GUARD_TEXT not in capsys.readouterr().err
