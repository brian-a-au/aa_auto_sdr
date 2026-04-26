"""Credential resolution precedence: profile > env > .env > config.json."""

import json
from pathlib import Path

import pytest

from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import ConfigError


def _write_profile(base: Path, name: str, data: dict) -> None:
    p = base / "orgs" / name
    p.mkdir(parents=True)
    (p / "config.json").write_text(json.dumps(data))


def test_profile_wins_over_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_profile(
        tmp_path,
        "prod",
        {
            "org_id": "P",
            "client_id": "Pc",
            "secret": "Ps",
            "scopes": "Px",
        },
    )
    monkeypatch.setenv("ORG_ID", "E")
    monkeypatch.setenv("CLIENT_ID", "Ec")
    monkeypatch.setenv("SECRET", "Es")
    monkeypatch.setenv("SCOPES", "Ex")

    creds = credentials.resolve(profile="prod", profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.org_id == "P"
    assert creds.source == "profile:prod"


def test_env_wins_over_config_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ORG_ID", "E")
    monkeypatch.setenv("CLIENT_ID", "Ec")
    monkeypatch.setenv("SECRET", "Es")
    monkeypatch.setenv("SCOPES", "Ex")
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "org_id": "F",
                "client_id": "Fc",
                "secret": "Fs",
                "scopes": "Fx",
            }
        )
    )
    creds = credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.org_id == "E"
    assert creds.source == "env"


def test_config_json_wins_when_nothing_else(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "org_id": "F",
                "client_id": "Fc",
                "secret": "Fs",
                "scopes": "Fx",
            }
        )
    )
    creds = credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.org_id == "F"
    assert creds.source == "config.json"


def test_aa_profile_env_var_picks_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_profile(
        tmp_path,
        "envdefault",
        {
            "org_id": "P",
            "client_id": "Pc",
            "secret": "Ps",
            "scopes": "Px",
        },
    )
    monkeypatch.setenv("AA_PROFILE", "envdefault")
    creds = credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.source == "profile:envdefault"


def test_explicit_profile_overrides_aa_profile_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_profile(
        tmp_path,
        "explicit",
        {
            "org_id": "X",
            "client_id": "Xc",
            "secret": "Xs",
            "scopes": "Xx",
        },
    )
    _write_profile(
        tmp_path,
        "envdefault",
        {
            "org_id": "Y",
            "client_id": "Yc",
            "secret": "Ys",
            "scopes": "Yx",
        },
    )
    monkeypatch.setenv("AA_PROFILE", "envdefault")
    creds = credentials.resolve(profile="explicit", profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.source == "profile:explicit"
    assert creds.org_id == "X"


def test_resolve_raises_when_no_source_provides_creds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ConfigError):
        credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)


def test_sandbox_propagates_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ORG_ID", "E")
    monkeypatch.setenv("CLIENT_ID", "Ec")
    monkeypatch.setenv("SECRET", "Es")
    monkeypatch.setenv("SCOPES", "Ex")
    monkeypatch.setenv("SANDBOX", "dev1")
    creds = credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.sandbox == "dev1"
