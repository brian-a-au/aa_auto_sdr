"""`--config`, `--format json` on the config commands, and the two results of `--profile-test`.

The sign-in request and the SDK are replaced in every test. Nothing here calls Adobe.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from aa_auto_sdr.api import sign_in
from aa_auto_sdr.api.sign_in import StepResult
from aa_auto_sdr.cli.commands import completion
from aa_auto_sdr.cli.commands import profiles as profiles_cmd
from aa_auto_sdr.cli.main import run
from aa_auto_sdr.core.credentials import Credentials
from aa_auto_sdr.core.exceptions import ApiError, AuthError, NoCompanyAccessError
from aa_auto_sdr.core.exit_codes import ExitCode

A = {
    "org_id": "A1B2C3D4E5F6A7B8C9D0E1F2@AdobeOrg",
    "client_id": "aaaa1111bbbb2222cccc3333dddd4444",
    "secret": "fake-secret-A-not-a-credential-0001",
    "scopes": "openid,AdobeID,additional_info.projectedProductContext",
}
B = {
    "org_id": "B9B8B7B6B5B4B3B2B1B0BABB@AdobeOrg",
    "client_id": "bbbb5555cccc6666dddd7777eeee8888",
    "secret": "fake-secret-B-not-a-credential-0002",
    "scopes": "openid,AdobeID,read_organizations",
}

posix_only = pytest.mark.skipif(os.name == "nt", reason="mode bits do not describe access on Windows")


def _write(path: Path, data: dict[str, Any], mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(mode)
    return path


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary home and working folder. Returns the working folder."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(work)
    return work


def _profile(tmp_path: Path, name: str, data: dict[str, Any], mode: int = 0o600) -> Path:
    return _write(tmp_path / "home" / ".aa" / "orgs" / name / "config.json", data, mode)


def _cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    capsys.readouterr()
    code = run(["--quiet", *argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- --config --------------------------------------------------------------


def test_config_flag_is_used_by_show_config(home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path / "cred.json", A)
    _write(home / "config.json", B)
    code, out, err = _cli(["--show-config", "--config", str(path)], capsys)
    assert code == ExitCode.OK.value
    assert out == (
        f"source:    config:{path}\n"
        f"org_id:    {A['org_id']}\n"
        "client_id: aaaa****4444\n"
        "secret:    ****\n"
        f"scopes:    {A['scopes']}\n"
    )
    assert err == ""


def test_config_flag_with_profile_is_a_usage_error(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path / "cred.json", A)
    _profile(tmp_path, "prod", B)
    for command in (["--show-config"], ["--config-status", "--format", "json"], ["--list-reportsuites"]):
        code, out, err = _cli([*command, "--profile", "prod", "--config", str(path)], capsys)
        assert code == ExitCode.USAGE.value
        assert out == ""
        assert err == "error: --profile and --config cannot be used together. Give one of them.\n"


def test_config_flag_beats_the_profile_variable(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path / "cred.json", A)
    _profile(tmp_path, "other", B)
    monkeypatch.setenv("AA_PROFILE", "other")
    code, out, _ = _cli(["--config-status", "--config", str(path)], capsys)
    assert code == ExitCode.OK.value
    assert f"  1. --config={path}" in out
    assert "aaaa****4444" in out


def test_config_flag_does_not_leak_into_the_next_run(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path / "cred.json", A)
    assert _cli(["--validate-config", "--config", str(path)], capsys)[0] == ExitCode.OK.value
    assert _cli(["--validate-config"], capsys)[0] == ExitCode.CONFIG.value


def test_config_flag_is_in_help_and_in_every_completion(capsys: pytest.CaptureFixture[str]) -> None:
    for shell, marker in (("bash", "--config "), ("zsh", "--config "), ("fish", "-l config\n")):
        assert completion.run_completion(shell) == 0
        assert marker in capsys.readouterr().out


def test_render_from_refuses_config(home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path / "cred.json", A)
    code, _, err = _cli(["--render-from", "x.json", "--config", str(path)], capsys)
    assert code == ExitCode.USAGE.value
    assert "--config" in err


# --- --show-config and --config-status ------------------------------------


def test_show_config_json_is_the_config_check(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(home / "config.json", A)
    code, out, err = _cli(["--show-config", "--format", "json"], capsys)
    report = json.loads(out)
    assert code == ExitCode.OK.value
    assert err == ""
    assert report["schema"] == "adobe-credentials/v1/config-check"
    assert report["tool"] == "aa_auto_sdr"
    assert report["product"] == "aa"
    assert report["ok"] is True
    assert report["credential"] == {
        "org_id": A["org_id"],
        "client_id": "aaaa****4444",
        "secret_set": True,
        "scopes": A["scopes"],
    }
    assert report["sources"] == [
        {
            "kind": "default_config",
            "name": "config.json",
            "path": str(home / "config.json"),
            "used": True,
            "fields": ["org_id", "client_id", "secret", "scopes"],
            "skipped": None,
        }
    ]


def test_show_config_json_with_no_credential(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _cli(["--show-config", "--format", "json"], capsys)
    report = json.loads(out)
    assert code == ExitCode.CONFIG.value
    assert report["ok"] is False
    assert report["credential"] == {"org_id": None, "client_id": None, "secret_set": False, "scopes": None}
    assert [p["code"] for p in report["problems"]] == ["no_credential"]
    assert "error: No credentials found." in err


def test_show_config_text_failure_is_unchanged(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _cli(["--show-config"], capsys)
    assert code == ExitCode.CONFIG.value
    assert out == ""
    assert "error: No credentials found." in err


@pytest.mark.parametrize("flag", ["--show-config", "--config-status"])
def test_agent_mode_alone_keeps_the_text_output(home: Path, capsys: pytest.CaptureFixture[str], flag: str) -> None:
    _write(home / "config.json", A)
    code, out, _ = _cli([flag, "--agent-mode"], capsys)
    assert code == ExitCode.OK.value
    assert "client_id: aaaa****4444" in out
    assert not out.lstrip().startswith("{")
    code, out, _ = _cli([flag, "--agent-mode", "--format", "json"], capsys)
    assert json.loads(out)["ok"] is True


def test_another_format_value_keeps_the_text_output(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(home / "config.json", A)
    code, out, _ = _cli(["--show-config", "--format", "excel"], capsys)
    assert code == ExitCode.OK.value
    assert out.startswith("source:    config.json\n")


def test_config_status_text_names_the_partial_source_and_the_file(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLIENT_ID", B["client_id"])
    path = _write(home / "config.json", A)
    code, out, err = _cli(["--config-status"], capsys)
    assert code == ExitCode.OK.value
    assert "  2. env vars                      ⊘ skipped (partial, missing: org_id, secret, scopes)" in out
    assert "  4. config.json (cwd)             ✓ MATCHED" in out
    assert f"  source:    config.json ({path})" in out
    assert "  secret:    ****" in out
    assert err.startswith(
        "notice: The environment variables set some credential fields and not ORG_ID, SECRET, SCOPES,"
    )
    assert A["secret"] not in out + err


def test_config_status_json_failure_keeps_the_exit_code(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write(home / "config.json", {"org_id": A["org_id"]})
    code, out, err = _cli(["--config-status", "--format", "json"], capsys)
    report = json.loads(out)
    assert code == ExitCode.CONFIG.value
    assert report["ok"] is False
    assert report["problems"][0]["code"] == "partial_source"
    assert report["problems"][0]["missing"] == ["client_id", "secret", "scopes"]
    assert report["sources"][0]["skipped"] == "partial"
    assert report["notices"] == []
    assert "resolution failed: No credentials found." in err


@posix_only
def test_profile_show_masks_and_warns_about_a_readable_file(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _profile(tmp_path, "prod", A, mode=0o644)
    code, out, err = _cli(["--profile-show", "prod"], capsys)
    assert code == ExitCode.OK.value
    assert "client_id:  aaaa****4444\n" in out
    assert "secret:     ****\n" in out
    assert A["secret"] not in out + err
    assert err.startswith(f"warning: {path} holds a credential")
    assert err.count("\n") == 1


def test_profile_show_refuses_an_invalid_name(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _cli(["--profile-show", "../other"], capsys)
    assert code == ExitCode.CONFIG.value
    assert out == ""
    assert "error: invalid profile name '../other'" in err


# --- --profile-test --------------------------------------------------------


class _Answer:
    def __init__(self, status: int, body: Any) -> None:
        self.status_code = status
        self._body = body

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _creds(secret: str = A["secret"]) -> Credentials:
    return Credentials(org_id=A["org_id"], client_id=A["client_id"], secret=secret, scopes=A["scopes"], source="x")


def _answer(monkeypatch: pytest.MonkeyPatch, status: int, body: Any) -> list[dict[str, str]]:
    sent: list[dict[str, str]] = []

    def fake_post(url: str, data: dict[str, str]) -> _Answer:
        sent.append({"url": url, **data})
        return _Answer(status, body)

    monkeypatch.setattr(sign_in, "_post", fake_post)
    return sent


def test_token_request_sends_the_credential_as_form_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _answer(monkeypatch, 200, {"access_token": "stub-token", "expires_in": 86399})
    assert sign_in.request_token(_creds()) == StepResult(ok=True)
    assert sent == [
        {
            "url": "https://ims-na1.adobelogin.com/ims/token/v3",
            "grant_type": "client_credentials",
            "client_id": A["client_id"],
            "client_secret": A["secret"],
            "scope": A["scopes"],
        }
    ]


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (200, {"page": "login"}, "unreachable"),
        (200, ValueError("not json"), "unreachable"),
        (200, ["access_token"], "unreachable"),
        (400, {"error": "invalid_client", "error_description": "invalid client_id parameter"}, "bad_client_id"),
        (401, {"error": "invalid_client", "error_description": "invalid client_secret parameter"}, "bad_secret"),
        (400, {"error": "invalid_client"}, "bad_client_id"),
        (400, {"error": "invalid_scope", "error_description": "scope is not allowed"}, "scopes_rejected"),
        (503, {"error": "server_error", "error_description": "try later"}, "sign_in_failed"),
        (502, ValueError("not json"), "sign_in_failed"),
    ],
)
def test_token_answer_codes(monkeypatch: pytest.MonkeyPatch, status: int, body: Any, code: str) -> None:
    _answer(monkeypatch, status, body)
    result = sign_in.request_token(_creds())
    assert (result.ok, result.code, result.no_answer) == (False, code, False)
    assert result.message


def test_network_error_is_unreachable_with_no_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    def fail(url: str, data: dict[str, str]) -> _Answer:
        raise requests.Timeout("timed out")

    monkeypatch.setattr(sign_in, "_post", fail)
    result = sign_in.request_token(_creds())
    assert (result.ok, result.code, result.no_answer) == (False, "unreachable", True)


def test_post_makes_one_form_request_with_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    seen: list[tuple[str, dict[str, str], Any]] = []

    def fake(url: str, *, data: dict[str, str], timeout: Any) -> _Answer:
        seen.append((url, data, timeout))
        return _Answer(200, {"access_token": "stub-token"})

    monkeypatch.setattr(requests, "post", fake)
    assert sign_in.request_token(_creds()).ok is True
    assert len(seen) == 1
    assert seen[0][0] == sign_in.IMS_SIGN_IN_URL
    assert seen[0][2] == (10, 60)


def test_adobe_message_is_cut_and_holds_no_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = A["secret"]
    description = f"client_secret={secret} was refused for {secret}. " + "x" * 400
    _answer(monkeypatch, 400, {"error": "other", "error_description": description})
    result = sign_in.request_token(_creds())
    assert result.code == "sign_in_failed"
    assert result.message is not None
    assert len(result.message) == 200
    assert secret not in result.message
    assert result.message.startswith("Adobe answered HTTP 400: client_secret=**** was refused for ****.")


@pytest.mark.parametrize(("body", "detail"), [({"error": "access_denied"}, "error access_denied"), ({}, "no message")])
def test_adobe_answer_without_a_description(monkeypatch: pytest.MonkeyPatch, body: Any, detail: str) -> None:
    _answer(monkeypatch, 403, body)
    assert sign_in.request_token(_creds()).message == f"Adobe answered HTTP 403: {detail}"


class _Client:
    company_id = "testco0"


def _company(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> list[Any]:
    from aa_auto_sdr.api import client as api_client

    calls: list[Any] = []

    def from_credentials(cls: Any, creds: Any, *, company_id: Any = None, retry_policy: Any = None) -> Any:
        calls.append(creds)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(api_client.AaClient, "from_credentials", classmethod(from_credentials))
    return calls


def test_profile_test_pass_reports_both_results(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _profile(tmp_path, "prod", A)
    _answer(monkeypatch, 200, {"access_token": "stub-token"})
    _company(monkeypatch, _Client())
    code, out, err = _cli(["--profile-test", "prod"], capsys)
    assert code == ExitCode.OK.value
    assert out == "sign-in: ok\ncompany check: ok\nPASS: profile 'prod' authenticated; company_id=testco0\n"
    assert "stub-token" not in out + err

    code, out, _ = _cli(["--profile-test", "prod", "--format", "json"], capsys)
    assert code == ExitCode.OK.value
    assert json.loads(out) == {
        "schema": "adobe-credentials/v1/live-test",
        "tool": "aa_auto_sdr",
        "tool_version": json.loads(out)["tool_version"],
        "product": "aa",
        "ok": True,
        "source": {"kind": "flag_profile", "name": "profile prod"},
        "profile": "prod",
        "sign_in": {"ok": True, "code": None, "message": None},
        "product_access": {"ok": True, "code": None, "message": None},
        "company_id": "testco0",
    }


def test_profile_test_failed_sign_in_does_not_run_the_company_check(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _profile(tmp_path, "prod", A)
    _answer(monkeypatch, 401, {"error": "invalid_client", "error_description": "invalid client_secret parameter"})
    calls = _company(monkeypatch, _Client())
    code, out, _ = _cli(["--profile-test", "prod"], capsys)
    assert code == ExitCode.AUTH.value
    lines = out.splitlines()
    assert lines[0].startswith("sign-in: FAIL [bad_secret] Adobe knows the client ID and rejected the secret.")
    assert lines[1] == "company check: not run"
    assert lines[2].startswith("FAIL [auth]: Adobe knows the client ID and rejected the secret.")
    assert calls == []


def test_profile_test_network_failure_at_sign_in_exits_with_the_api_code(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _profile(tmp_path, "prod", A)
    monkeypatch.setattr(profiles_cmd, "request_token", lambda _c: sign_in._failed("unreachable", no_answer=True))
    code, out, _ = _cli(["--profile-test", "prod", "--format", "json"], capsys)
    report = json.loads(out)
    assert code == ExitCode.API.value
    assert report["sign_in"]["code"] == "unreachable"
    assert report["product_access"] == {"ok": None, "code": None, "message": None}
    code, out, _ = _cli(["--profile-test", "prod"], capsys)
    assert "FAIL [api]: " in out


@pytest.mark.parametrize(
    ("error", "code", "exit_code", "label"),
    [
        (NoCompanyAccessError("this credential sees no Analytics company"), "no_product_access", ExitCode.AUTH, "auth"),
        (AuthError("no globalCompanyId"), "unreachable", ExitCode.AUTH, "auth"),
        (ApiError("auth bootstrap failed"), "unreachable", ExitCode.API, "api"),
    ],
)
def test_profile_test_company_check_failures(
    home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    code: str,
    exit_code: ExitCode,
    label: str,
) -> None:
    _profile(tmp_path, "prod", A)
    _answer(monkeypatch, 200, {"access_token": "stub-token"})
    _company(monkeypatch, error)
    rc, out, _ = _cli(["--profile-test", "prod"], capsys)
    assert rc == exit_code.value
    assert out == f"sign-in: ok\ncompany check: FAIL [{code}] {error}\nFAIL [{label}]: {error}\n"
    rc, out, _ = _cli(["--profile-test", "prod", "--format", "json"], capsys)
    report = json.loads(out)
    assert rc == exit_code.value
    assert report["ok"] is False
    assert report["sign_in"] == {"ok": True, "code": None, "message": None}
    assert report["product_access"] == {"ok": False, "code": code, "message": str(error)}


def test_profile_test_config_failure(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _cli(["--profile-test", "missing"], capsys)
    assert code == ExitCode.CONFIG.value
    assert out.startswith("FAIL [config]: Profile 'missing' not found")
    assert "sign-in" not in out
    code, out, _ = _cli(["--profile-test", "missing", "--format", "json"], capsys)
    report = json.loads(out)
    assert code == ExitCode.CONFIG.value
    assert report["ok"] is False
    assert report["sign_in"] == {"ok": None, "code": None, "message": None}
    assert [p["code"] for p in report["problems"]] == ["profile_not_found"]


def test_profile_test_agent_mode_alone_keeps_the_text_output(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _profile(tmp_path, "prod", A)
    _answer(monkeypatch, 200, {"access_token": "stub-token"})
    _company(monkeypatch, _Client())
    code, out, _ = _cli(["--profile-test", "prod", "--agent-mode"], capsys)
    assert code == ExitCode.OK.value
    assert out.endswith("PASS: profile 'prod' authenticated; company_id=testco0\n")


def test_no_company_message_is_the_same_in_every_command() -> None:
    """Rule L2.6: one message for "no access". The SDK bootstrap raises it for every command."""
    from unittest.mock import MagicMock, patch

    from aa_auto_sdr.api.client import AaClient

    login = MagicMock()
    login.getCompanyId.return_value = []
    with (
        patch("aanalytics2.configure"),
        patch("aanalytics2.Login", return_value=login),
        pytest.raises(NoCompanyAccessError) as caught,
    ):
        AaClient.from_credentials(_creds())
    assert str(caught.value) == (
        "Sign-in worked, but this credential sees no Analytics company. In the Adobe Admin Console, "
        "add the credential's technical account to an Analytics product profile."
    )


# --- the profile name and per-profile folders ------------------------------

_UNSAFE_NAMES = ["../x", "..", ".", "a/b", "a\\b", "/etc/passwd"]


@pytest.mark.parametrize("name", _UNSAFE_NAMES)
@pytest.mark.parametrize(
    "command",
    [
        ["--list-snapshots"],
        ["--prune-snapshots", "--keep-last", "1", "--dry-run"],
        ["--diff", "rs1@latest", "rs1@previous"],
        ["rs1", "--trending-window", "30d"],
        ["rs1", "--compare-with-prev"],
        ["--render-from", "rs1@latest"],
        ["rs1", "--snapshot"],
        ["rs1", "--watch", "--interval", "1h"],
        ["--batch", "rs1", "rs2", "--auto-snapshot"],
    ],
    ids=" ".join,
)
def test_unsafe_profile_name_never_reaches_a_snapshot_path(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], command: list[str], name: str
) -> None:
    code, out, err = _cli([*command, "--profile", name], capsys)
    assert code == ExitCode.CONFIG.value
    assert out == ""
    assert f"error: invalid profile name '{name}'" in err
    assert not (tmp_path / "home").exists(), "a folder was created from the name"
    assert [p.name for p in tmp_path.iterdir()] == ["work"]


@pytest.mark.parametrize("name", [*_UNSAFE_NAMES, "", "my store", ".hidden"])
def test_snapshot_dir_refuses_an_invalid_name(home: Path, name: str) -> None:
    from aa_auto_sdr.cli.commands import diff, render_from, snapshots, trending
    from aa_auto_sdr.cli.commands._shared import resolve_snapshot_dir
    from aa_auto_sdr.core import profiles
    from aa_auto_sdr.core.exceptions import ConfigError

    with pytest.raises(ConfigError, match="invalid profile name"):
        profiles.snapshot_dir(name)
    if not name:
        return  # an empty --profile means "no profile" to the commands below
    import argparse

    calls = [
        lambda: resolve_snapshot_dir(argparse.Namespace(snapshot_dir=None, profile=name)),
        lambda: snapshots.list_run(profile=name, rsid=None, format_name=None, snapshot_dir=None),
        lambda: trending._resolve_snapshot_dir(snapshot_dir=None, profile=name),
        lambda: diff.compute_report(
            a="rs1@latest",
            b="rs1@previous",
            profile=name,
            snapshot_dir=None,
            reverse=False,
            ignore_fields=frozenset(),
            extended_fields=False,
        ),
        lambda: render_from._load_token("rs1@latest", profile=name, snapshot_dir=None),
    ]
    for call in calls:
        with pytest.raises(ConfigError, match="invalid profile name"):
            call()


def test_snapshot_folder_under_an_old_style_name_still_works_with_one_warning(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from aa_auto_sdr.core import profiles

    store = tmp_path / "home" / ".aa" / "orgs" / "my store" / "snapshots"
    store.mkdir(parents=True)
    code, _, err = _cli(["--list-snapshots", "--profile", "my store"], capsys)
    assert code == ExitCode.OK.value
    assert err.count("\n") == 1
    assert err.startswith("warning: profile name 'my store' breaks the profile name rule")
    assert profiles.snapshot_dir("my store") == store


def test_valid_profile_name_with_no_folder_is_accepted_for_snapshots(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = _cli(["--list-snapshots", "--profile", "prod"], capsys)
    assert code == ExitCode.OK.value
    assert err == ""


@pytest.mark.parametrize("command", [["--validate-config"], ["--show-config"], ["--config-status"]], ids=" ".join)
def test_empty_profile_flag_means_no_profile(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: list[str]
) -> None:
    # e.g. `--profile "$NAME"` with NAME unset. The lookup goes on to the other sources, as before.
    for name, value in A.items():
        monkeypatch.setenv(name.upper(), value)
    code, _, err = _cli([*command, "--profile", ""], capsys)
    assert code == ExitCode.OK.value
    assert err == ""


def test_empty_profile_flag_falls_back_to_the_profile_variable(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _profile(tmp_path, "prod", B)
    monkeypatch.setenv("AA_PROFILE", "prod")
    code, out, _ = _cli(["--show-config", "--profile", ""], capsys)
    assert code == ExitCode.OK.value
    assert out.startswith("source:    profile:prod\n")


def test_empty_profile_flag_with_a_config_file_is_not_an_error(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path / "cred.json", A)
    code, out, _ = _cli(["--show-config", "--profile", "", "--config", str(path)], capsys)
    assert code == ExitCode.OK.value
    assert out.startswith(f"source:    config:{path}\n")


def test_empty_profile_flag_uses_the_default_snapshot_folder(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = _cli(["--list-snapshots", "--profile", ""], capsys)
    assert code == ExitCode.CONFIG.value
    assert err == "error: --list-snapshots requires --profile or --snapshot-dir\n"


def test_config_check_reports_an_invalid_name_as_json(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _cli(["--config-status", "--format", "json", "--profile", "../x"], capsys)
    assert code == ExitCode.CONFIG.value
    assert [p["code"] for p in json.loads(out)["problems"]] == ["invalid_profile_name"]
