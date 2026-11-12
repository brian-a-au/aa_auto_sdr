"""--profile-add and --show-config handlers."""

import json
from pathlib import Path

import pytest

from aa_auto_sdr.cli.commands import config as cmd


def test_profile_add_writes_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--profile-add reads from stdin in interactive mode; we feed it a script.

    v1.2.2: the SANDBOX prompt is removed; --profile-add now asks for exactly
    four fields (ORG_ID, CLIENT_ID, SECRET, SCOPES)."""
    inputs = iter(["O@AdobeOrg", "Cid", "Sec", "Scp"])
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(inputs))
    rc = cmd.profile_add("prod", base=tmp_path)
    assert rc == 0
    cfg_path = tmp_path / "orgs" / "prod" / "config.json"
    assert cfg_path.exists()
    cfg = json.loads(cfg_path.read_text())
    assert cfg["org_id"] == "O@AdobeOrg"
    assert cfg["client_id"] == "Cid"
    assert cfg["secret"] == "Sec"
    assert cfg["scopes"] == "Scp"
    assert "sandbox" not in cfg


def test_profile_add_stops_cleanly_when_input_ends(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    """Ctrl+D, or stdin that is closed or empty, ends input before all four
    fields: a config error (exit 10) and no profile, not an EOFError traceback."""

    def eof(*_a, **_k):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    rc = cmd.profile_add("prod", base=tmp_path)
    assert rc == 10
    assert "input ended" in capsys.readouterr().err
    assert not (tmp_path / "orgs" / "prod").exists()


def test_profile_add_ctrl_c_exits_130_without_writing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    """The prompt says "Press Ctrl+C to cancel": Ctrl+C is a clean cancel
    (exit 130, one stderr line, no profile), not a KeyboardInterrupt traceback."""

    def interrupt(*_a, **_k):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", interrupt)
    rc = cmd.profile_add("prod", base=tmp_path)
    assert rc == 130
    assert capsys.readouterr().err == "cancelled; profile not written\n"
    assert not (tmp_path / "orgs" / "prod").exists()


def test_profile_add_ctrl_c_after_some_answers_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    answers = iter(["O@AdobeOrg", "Cid"])

    def answer_then_interrupt(*_a, **_k):
        try:
            return next(answers)
        except StopIteration:
            raise KeyboardInterrupt from None

    monkeypatch.setattr("builtins.input", answer_then_interrupt)
    rc = cmd.profile_add("prod", base=tmp_path)
    assert rc == 130
    assert "cancelled; profile not written" in capsys.readouterr().err
    assert not (tmp_path / "orgs" / "prod").exists()


@pytest.mark.parametrize(
    ("answers", "field"),
    [
        (["", "Cid", "Sec", "Scp"], "ORG_ID"),
        (["O@AdobeOrg", "   ", "Sec", "Scp"], "CLIENT_ID"),
        (["O@AdobeOrg", "Cid", "", "Scp"], "SECRET"),
        (["O@AdobeOrg", "Cid", "Sec", " \t "], "SCOPES"),
    ],
)
def test_profile_add_rejects_an_empty_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys, answers: list[str], field: str
) -> None:
    """An empty or blank answer is a config error (exit 10) naming the field,
    and no profile is written."""
    inputs = iter(answers)
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(inputs))
    rc = cmd.profile_add("prod", base=tmp_path)
    assert rc == 10
    err = capsys.readouterr().err
    assert f"error: {field} is empty" in err
    assert not (tmp_path / "orgs" / "prod").exists()


@pytest.mark.parametrize("name", ["", "../../escape", "a/b", "a\\b", "..", "."])
def test_profile_add_rejects_an_unsafe_name_before_prompting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys, name: str
) -> None:
    """The name becomes a folder under orgs/. A name that is empty, '.' or '..',
    or holds a path separator is refused (exit 10) before any prompt, and
    nothing is written anywhere."""
    base = tmp_path / "home" / ".aa"
    prompts: list[str] = []

    def record(prompt: str = "") -> str:
        prompts.append(prompt)
        return "v"

    monkeypatch.setattr("builtins.input", record)
    rc = cmd.profile_add(name, base=base)
    assert rc == 10
    captured = capsys.readouterr()
    assert f"error: invalid profile name '{name}'" in captured.err
    assert prompts == []
    assert captured.out == ""
    assert list(tmp_path.rglob("config.json")) == []
    assert not base.exists()


def test_show_config_prints_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")
    monkeypatch.chdir(tmp_path)
    rc = cmd.show_config(profile=None, profiles_base=tmp_path)
    assert rc == 0
    captured = capsys.readouterr()
    assert "env" in captured.out


def test_config_status_renders_canonical_scopes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--config-status renders resolved scopes in the canonical no-space
    comma form, regardless of how they were entered."""
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "Cid12345")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "openid, AdobeID, additional_info.projectedProductContext")
    monkeypatch.chdir(tmp_path)
    rc = cmd.config_status(profile=None)
    assert rc == 0
    out = capsys.readouterr().out
    assert "openid,AdobeID,additional_info.projectedProductContext" in out
    assert "openid, AdobeID" not in out


def test_config_status_does_not_mutate_auth_scopes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The canonical render is display-only: the resolved Credentials.scopes
    used for auth keeps the value as entered (spaces included)."""
    from aa_auto_sdr.core import credentials

    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "Cid12345")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "openid, AdobeID, additional_info.projectedProductContext")
    monkeypatch.chdir(tmp_path)
    rc = cmd.config_status(profile=None)
    assert rc == 0
    out = capsys.readouterr().out
    # Display normalized to canonical no-space form ...
    assert "openid,AdobeID,additional_info.projectedProductContext" in out
    # ... but the value used for auth is unchanged (spaces preserved).
    creds = credentials.resolve(profile=None)
    assert creds.scopes == "openid, AdobeID, additional_info.projectedProductContext"


def test_show_config_returns_config_error_when_no_creds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = cmd.show_config(profile=None, profiles_base=tmp_path)
    assert rc == 10


def test_show_config_does_not_print_sandbox_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """v1.2.2: --show-config no longer prints a sandbox: line."""
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")
    monkeypatch.chdir(tmp_path)
    rc = cmd.show_config(profile=None, profiles_base=tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "sandbox" not in out.lower()


def test_sample_config_emits_four_keys_with_comma_separated_scopes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """v1.2.3: --sample-config emits {org_id, client_id, secret, scopes} only,
    with no-space comma-separated scopes (the canonical form per
    docs/CONFIGURATION.md; matches every user-facing example in README /
    QUICKSTART / CONFIGURATION)."""
    rc = cmd.sample_config()
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload.keys()) == {"org_id", "client_id", "secret", "scopes"}
    assert payload["scopes"] == "openid,AdobeID,additional_info.projectedProductContext"


@pytest.mark.parametrize("env_set", [True, False])
def test_config_status_reports_a_damaged_config_json_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys, env_set: bool
) -> None:
    for var, value in (("ORG_ID", "O"), ("CLIENT_ID", "C"), ("SECRET", "S"), ("SCOPES", "X")):
        if env_set:
            monkeypatch.setenv(var, value)
        else:
            monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("AA_PROFILE", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text("[1]")
    rc = cmd.config_status(profile=None)
    out = capsys.readouterr().out
    assert "Resolution chain" in out
    # Env vars outrank config.json, so a damaged file only fails resolution when nothing else resolves.
    assert rc == (0 if env_set else 10)
