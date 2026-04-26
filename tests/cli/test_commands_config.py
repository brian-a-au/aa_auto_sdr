"""--profile-add and --show-config handlers."""

import json
from pathlib import Path

import pytest

from aa_auto_sdr.cli.commands import config as cmd


def test_profile_add_writes_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """--profile-add reads from stdin in interactive mode; we feed it a script."""
    inputs = iter(["O@AdobeOrg", "Cid", "Sec", "Scp", ""])
    monkeypatch.setattr("builtins.input", lambda *_a, **_k: next(inputs))
    rc = cmd.profile_add("prod", base=tmp_path)
    assert rc == 0
    cfg_path = tmp_path / "orgs" / "prod" / "config.json"
    assert cfg_path.exists()
    cfg = json.loads(cfg_path.read_text())
    assert cfg["org_id"] == "O@AdobeOrg"
    assert cfg["sandbox"] is None  # blank input → null


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
