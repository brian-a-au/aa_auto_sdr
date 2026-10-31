"""Credential resolution precedence: profile > env > .env > config.json."""

import json
import os
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


def test_dotenv_resolves_with_uppercase_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A .env copied from .env.example uses UPPERCASE keys (ORG_ID, ...), matching
    the env-var contract. `_from_dotenv` must normalize them to the lowercase keys
    `_from_dict` expects, the same way `_from_env` maps `ORG_ID` -> `org_id`."""
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / ".env").write_text(
        "ORG_ID=D@AdobeOrg\nCLIENT_ID=Dc\nSECRET=Ds\nSCOPES=Dx\n",
    )
    creds = credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.source == ".env"
    assert creds.org_id == "D@AdobeOrg"
    assert creds.client_id == "Dc"
    assert creds.secret == "Ds"
    assert creds.scopes == "Dx"


def test_resolve_raises_when_no_source_provides_creds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ConfigError):
        credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)


def test_legacy_sandbox_key_in_config_is_ignored(tmp_path: Path) -> None:
    """Forward-compat: pre-1.2.2 config.json files contain `"sandbox": null`
    (or any value). After v1.2.2 the field is gone from `Credentials`, but the
    loader silently ignores the unknown key."""
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "org_id": "F",
                "client_id": "Fc",
                "secret": "Fs",
                "scopes": "Fx",
                "sandbox": "legacy-value",
            }
        )
    )
    creds = credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    assert creds.org_id == "F"
    assert creds.scopes == "Fx"
    assert not hasattr(creds, "sandbox")


def test_from_dotenv_returns_none_when_python_dotenv_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When python-dotenv is not installed, `_from_dotenv` swallows the
    ImportError and returns None so resolution falls through to the next source."""
    import sys

    # Force `from dotenv import dotenv_values` to raise ImportError.
    monkeypatch.setitem(sys.modules, "dotenv", None)
    (tmp_path / ".env").write_text("ORG_ID=O\n")
    assert credentials._from_dotenv(tmp_path) is None


def test_resolution_chain_reports_unmatched_profile_entry(tmp_path: Path) -> None:
    """A profile that resolves to a missing config.json is reported as an
    unmatched priority-1 entry rather than skipped."""
    chain = credentials.resolution_chain(
        profile="ghost",
        profiles_base=tmp_path,
        working_dir=tmp_path,
    )
    profile_entry = chain[0]
    assert profile_entry.priority == 1
    assert "ghost" in profile_entry.source
    assert profile_entry.matched is False


@pytest.mark.parametrize("content", [b"{not json", b"[1]", b"\xff\xfe{}"])
def test_damaged_config_json_raises_config_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: bytes
) -> None:
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "config.json").write_bytes(content)
    with pytest.raises(ConfigError, match=r"config\.json"):
        credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)


def test_unreadable_config_json_raises_config_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    # A directory where the file should be fails to open on every OS, like an unreadable file.
    (tmp_path / "config.json").mkdir()
    with pytest.raises(ConfigError, match="could not read"):
        credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs POSIX permissions and a non-root user")
def test_unreadable_dotenv_raises_config_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("ORG_ID=x\n")
    dotenv.chmod(0)
    try:
        with pytest.raises(ConfigError, match="could not read"):
            credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    finally:
        dotenv.chmod(0o600)


def test_damaged_profile_raises_config_error(tmp_path: Path) -> None:
    profile_dir = tmp_path / "orgs" / "bad"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.json").write_text("[]")
    with pytest.raises(ConfigError, match="bad"):
        credentials.resolve(profile="bad", profiles_base=tmp_path, working_dir=tmp_path)


def test_non_utf8_dotenv_raises_config_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / ".env").write_bytes(b"ORG_ID=\xff\xfe\n")
    with pytest.raises(ConfigError, match="not valid UTF-8"):
        credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)


def test_null_credential_value_counts_as_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """JSON null (or a bare `SECRET` line in .env) must not become the text "None"."""
    for var in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    (tmp_path / "config.json").write_text(
        json.dumps({"org_id": "O@AdobeOrg", "client_id": "C", "secret": None, "scopes": "openid"})
    )
    # The file is incomplete, so it is skipped and resolution fails (exit 10)
    # instead of sending the literal secret "None" to Adobe.
    with pytest.raises(ConfigError):
        credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)


def test_resolution_chain_matches_resolve_when_an_env_var_is_blank(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # resolve() strips values before deciding env vars are complete; the
    # --config-status chain must reach the same answer.
    for var in ("ORG_ID", "CLIENT_ID", "AA_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ORG_ID", "x@AdobeOrg")
    monkeypatch.setenv("CLIENT_ID", "x")
    monkeypatch.setenv("SECRET", "   ")
    monkeypatch.setenv("SCOPES", "openid")
    (tmp_path / "config.json").write_text(
        json.dumps({"org_id": "o@AdobeOrg", "client_id": "c", "secret": "s", "scopes": "openid"})
    )
    resolved = credentials.resolve(profile=None, profiles_base=tmp_path, working_dir=tmp_path)
    chain = credentials.resolution_chain(profiles_base=tmp_path, working_dir=tmp_path)
    assert resolved.source == "config.json"
    assert [e.source for e in chain if e.matched] == ["config.json (cwd)"]
