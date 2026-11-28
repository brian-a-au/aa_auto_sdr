"""Pins which source wins the credential lookup.

These tests were written against the lookup as it was before the credentials
standard work, and they passed unchanged after it. They use only the public
`resolve()` call, so they hold the result steady across a rewrite of the code
behind it. Each case checks the winning source and the credential it gave.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_auto_sdr.core import credentials
from aa_auto_sdr.core.exceptions import ConfigError

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
C = {
    "org_id": "C0C1C2C3C4C5C6C7C8C9CACB@AdobeOrg",
    "client_id": "cccc9999dddd0000eeee1111ffff2222",
    "secret": "fake-secret-C-not-a-credential-0003",
    "scopes": "openid,AdobeID",
}
D = {
    "org_id": "D0D1D2D3D4D5D6D7D8D9DADB@AdobeOrg",
    "client_id": "dddd3333eeee4444ffff5555aaaa6666",
    "secret": "fake-secret-D-not-a-credential-0004",
    "scopes": "openid",
}

_VARS = ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE")


def _without(cred: dict[str, str], *fields: str) -> dict[str, str]:
    return {k: v for k, v in cred.items() if k not in fields}


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    for var in _VARS:
        monkeypatch.delenv(var, raising=False)
    home = tmp_path / "home"
    work = tmp_path / "parent" / "work"
    home.mkdir()
    work.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    return World(home=home, work=work, monkeypatch=monkeypatch)


class World:
    def __init__(self, *, home: Path, work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.home = home
        self.work = work
        self.base = home / ".aa"
        self._monkeypatch = monkeypatch

    def profile(self, name: str, cred: dict[str, str]) -> None:
        folder = self.base / "orgs" / name
        folder.mkdir(parents=True)
        (folder / "config.json").write_text(json.dumps(cred))

    def env(self, cred: dict[str, str]) -> None:
        for key, value in cred.items():
            self._monkeypatch.setenv(key.upper(), value)

    def setenv(self, name: str, value: str) -> None:
        self._monkeypatch.setenv(name, value)

    def dotenv(self, cred: dict[str, str], *, folder: Path | None = None, extra: str = "") -> None:
        lines = [f"{key.upper()}={value}" for key, value in cred.items()]
        ((folder or self.work) / ".env").write_text("\n".join(lines) + "\n" + extra)

    def config(self, cred: dict[str, str]) -> None:
        (self.work / "config.json").write_text(json.dumps(cred))

    def resolve(self, profile: str | None = None) -> credentials.Credentials:
        return credentials.resolve(profile=profile, profiles_base=self.base, working_dir=self.work)

    def winner(self, profile: str | None = None) -> tuple[str, dict[str, str]]:
        creds = self.resolve(profile)
        return creds.source, {
            "org_id": creds.org_id,
            "client_id": creds.client_id,
            "secret": creds.secret,
            "scopes": creds.scopes,
        }


def test_flag_profile_beats_every_other_source(world: World) -> None:
    world.profile("prod", A)
    world.profile("other", B)
    world.setenv("AA_PROFILE", "other")
    world.env(C)
    world.dotenv(D)
    world.config(D)
    assert world.winner("prod") == ("profile:prod", A)


def test_profile_variable_beats_environment_dotenv_and_config(world: World) -> None:
    world.profile("prod", A)
    world.setenv("AA_PROFILE", "prod")
    world.env(B)
    world.dotenv(C)
    world.config(D)
    assert world.winner() == ("profile:prod", A)


def test_empty_profile_variable_is_not_a_profile(world: World) -> None:
    world.setenv("AA_PROFILE", "")
    world.env(A)
    assert world.winner() == ("env", A)


def test_environment_beats_dotenv_and_config(world: World) -> None:
    world.env(A)
    world.dotenv(B)
    world.config(C)
    assert world.winner() == ("env", A)


def test_dotenv_beats_config(world: World) -> None:
    world.dotenv(A)
    world.config(B)
    assert world.winner() == (".env", A)


def test_dotenv_alone(world: World) -> None:
    world.dotenv(A)
    assert world.winner() == (".env", A)


def test_config_alone(world: World) -> None:
    world.config(A)
    assert world.winner() == ("config.json", A)


@pytest.mark.parametrize("missing", ["org_id", "client_id", "secret", "scopes"])
def test_partial_environment_is_skipped_for_dotenv(world: World, missing: str) -> None:
    world.env(_without(A, missing))
    world.dotenv(B)
    world.config(C)
    assert world.winner() == (".env", B)


@pytest.mark.parametrize("missing", ["org_id", "client_id", "secret", "scopes"])
def test_partial_environment_is_skipped_for_config(world: World, missing: str) -> None:
    world.env(_without(A, missing))
    world.config(B)
    assert world.winner() == ("config.json", B)


def test_partial_environment_and_partial_dotenv_are_skipped_for_config(world: World) -> None:
    world.env(_without(A, "secret", "scopes"))
    world.dotenv(_without(B, "org_id"))
    world.config(C)
    assert world.winner() == ("config.json", C)


def test_fields_are_never_mixed_between_sources(world: World) -> None:
    # Together the two partial sources hold all four fields. Neither is used.
    world.env(_without(A, "secret", "scopes"))
    world.dotenv(_without(B, "org_id", "client_id"))
    with pytest.raises(ConfigError, match="No credentials found"):
        world.resolve()


def test_blank_environment_variable_counts_as_missing(world: World) -> None:
    world.env({**A, "secret": "   "})
    world.config(B)
    assert world.winner() == ("config.json", B)


def test_blank_dotenv_value_counts_as_missing(world: World) -> None:
    world.dotenv({**A, "scopes": ""})
    world.config(B)
    assert world.winner() == ("config.json", B)


def test_dotenv_in_a_parent_folder_is_not_read(world: World) -> None:
    world.dotenv(B, folder=world.work.parent)
    world.config(A)
    assert world.winner() == ("config.json", A)


def test_dotenv_in_a_parent_folder_alone_gives_no_credential(world: World) -> None:
    world.dotenv(B, folder=world.work.parent)
    with pytest.raises(ConfigError, match="No credentials found"):
        world.resolve()


def test_dotenv_cannot_set_the_profile_variable(world: World) -> None:
    world.profile("other", B)
    world.dotenv(A, extra="AA_PROFILE=other\n")
    assert world.winner() == (".env", A)


def test_nothing_set_is_an_error(world: World) -> None:
    with pytest.raises(ConfigError, match="No credentials found"):
        world.resolve()


def test_partial_config_alone_is_an_error(world: World) -> None:
    world.config(_without(A, "scopes"))
    with pytest.raises(ConfigError, match="No credentials found"):
        world.resolve()


def test_missing_flag_profile_is_an_error_with_no_fall_back(world: World) -> None:
    world.env(B)
    world.dotenv(B)
    world.config(B)
    with pytest.raises(ConfigError, match="Profile 'missing' not found"):
        world.resolve("missing")


def test_missing_profile_variable_target_is_an_error_with_no_fall_back(world: World) -> None:
    world.setenv("AA_PROFILE", "missing")
    world.env(B)
    world.config(B)
    with pytest.raises(ConfigError, match="Profile 'missing' not found"):
        world.resolve()


def test_partial_profile_is_an_error_with_no_fall_back(world: World) -> None:
    world.profile("prod", _without(A, "scopes"))
    world.env(B)
    world.config(B)
    with pytest.raises(ConfigError, match="Missing required credential fields: scopes"):
        world.resolve("prod")


def test_damaged_profile_is_an_error_with_no_fall_back(world: World) -> None:
    folder = world.base / "orgs" / "prod"
    folder.mkdir(parents=True)
    (folder / "config.json").write_text("{not json")
    world.env(B)
    with pytest.raises(ConfigError, match="prod"):
        world.resolve("prod")


def test_damaged_config_does_not_matter_when_the_environment_wins(world: World) -> None:
    world.env(A)
    (world.work / "config.json").write_text("{not json")
    assert world.winner() == ("env", A)


def test_damaged_config_does_not_matter_when_dotenv_wins(world: World) -> None:
    world.dotenv(A)
    (world.work / "config.json").write_text("{not json")
    assert world.winner() == (".env", A)


def test_damaged_config_is_an_error_when_nothing_outranks_it(world: World) -> None:
    world.env(_without(A, "secret"))
    (world.work / "config.json").write_text("{not json")
    with pytest.raises(ConfigError, match=r"config\.json"):
        world.resolve()


def test_profile_does_not_read_the_working_folder(world: World) -> None:
    world.profile("prod", A)
    (world.work / "config.json").write_text("{not json")
    (world.work / ".env").write_bytes(b"ORG_ID=\xff\xfe\n")
    assert world.winner("prod") == ("profile:prod", A)


def test_values_are_stripped_and_otherwise_unchanged(world: World) -> None:
    spaced = {**A, "scopes": "  AdobeID, openid ,additional_info.projectedProductContext  "}
    world.config(spaced)
    source, cred = world.winner()
    assert source == "config.json"
    assert cred["scopes"] == "AdobeID, openid ,additional_info.projectedProductContext"


def test_upper_case_keys_in_a_json_file_are_not_read(world: World) -> None:
    world.config({key.upper(): value for key, value in A.items()})
    with pytest.raises(ConfigError, match="No credentials found"):
        world.resolve()


def test_sandbox_and_other_keys_in_a_file_are_ignored(world: World) -> None:
    world.profile("prod", {**A, "sandbox": "dev", "note": "x"})
    assert world.winner("prod") == ("profile:prod", A)
