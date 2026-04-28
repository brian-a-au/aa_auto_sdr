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
    """v1.2.2: --sample-config emits {org_id, client_id, secret, scopes} only,
    with comma-separated scopes (matches every user-facing example in the docs)."""
    rc = cmd.sample_config()
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload.keys()) == {"org_id", "client_id", "secret", "scopes"}
    assert payload["scopes"] == "openid, AdobeID, additional_info.projectedProductContext"
