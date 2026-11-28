"""Notices, warnings, `--config` and profile name checks of the credential lookup.

The shared cases in `tests/test_standard_cases.py` cover the rules of the
Adobe credentials standard. These tests cover what is particular to this tool.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from aa_auto_sdr.core import credentials, notices, profiles
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

posix_only = pytest.mark.skipif(os.name == "nt", reason="mode bits do not describe access on Windows")


def _write(path: Path, data: dict[str, object], mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(mode)
    return path


def _dotenv(folder: Path, cred: dict[str, str]) -> None:
    path = folder / ".env"
    path.write_text("".join(f"{k.upper()}={v}\n" for k, v in cred.items()), encoding="utf-8")
    path.chmod(0o600)


def _resolve(tmp_path: Path, **kwargs: object) -> credentials.Credentials:
    return credentials.resolve(profiles_base=tmp_path / ".aa", working_dir=tmp_path, **kwargs)


def _lookup(tmp_path: Path, **kwargs: object) -> credentials.Lookup:
    return credentials.lookup(profiles_base=tmp_path / ".aa", working_dir=tmp_path, **kwargs)


# --- notices ---------------------------------------------------------------


def test_notice_line_is_printed_once_per_run(capsys: pytest.CaptureFixture[str]) -> None:
    notices.say("notice", "one")
    notices.say("notice", "one")
    notices.say("warning", "one")
    assert capsys.readouterr().err == "notice: one\nwarning: one\n"
    notices.reset()
    notices.say("notice", "one")
    assert capsys.readouterr().err == "notice: one\n"


def test_different_dotenv_and_config_gives_a_notice_and_dotenv_wins(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _dotenv(tmp_path, A)
    _write(tmp_path / "config.json", B)
    first = _resolve(tmp_path)
    second = _resolve(tmp_path)
    assert first.source == second.source == ".env"
    assert first.client_id == A["client_id"]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"notice: The .env file and the config.json file in {tmp_path} hold different credentials. "
        "This run uses the .env file.\n"
    )


def test_same_credential_in_dotenv_and_config_gives_no_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _dotenv(tmp_path, A)
    _write(tmp_path / "config.json", A)
    assert _resolve(tmp_path).source == ".env"
    assert capsys.readouterr().err == ""


def test_partial_config_beside_a_complete_dotenv_gives_no_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _dotenv(tmp_path, A)
    _write(tmp_path / "config.json", {"org_id": B["org_id"]})
    assert _resolve(tmp_path).source == ".env"
    assert capsys.readouterr().err == ""


def test_partial_environment_gives_a_notice_that_names_the_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ORG_ID", A["org_id"])
    monkeypatch.setenv("CLIENT_ID", A["client_id"])
    _write(tmp_path / "config.json", B)
    assert _resolve(tmp_path).source == "config.json"
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert err.startswith("notice: The environment variables set some credential fields and not SECRET, SCOPES,")


def test_partial_dotenv_gives_a_notice(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _dotenv(tmp_path, {"org_id": A["org_id"]})
    _write(tmp_path / "config.json", B)
    found = _lookup(tmp_path)
    assert found.creds is not None
    assert found.creds.source == "config.json"
    assert [(n.code, n.missing) for n in found.notices] == [
        ("partial_source_skipped", ("client_id", "secret", "scopes"))
    ]
    assert capsys.readouterr().err == ""  # lookup() reports, and only announce() prints


def test_dotenv_with_no_credential_field_is_not_a_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / ".env").write_text("NOTION_TOKEN=fake-notion-value\nLOG_LEVEL=INFO\n", encoding="utf-8")
    _write(tmp_path / "config.json", A)
    found = _lookup(tmp_path, scan_all=True)
    assert [s.kind for s in found.sources] == ["default_config"]
    assert found.notices == []
    assert found.warnings == []


def test_lookup_that_fails_names_the_partial_sources_in_the_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SECRET", A["secret"])
    _write(tmp_path / "config.json", {k: v for k, v in A.items() if k != "scopes"})
    found = _lookup(tmp_path)
    assert found.creds is None
    assert found.error is not None
    assert found.error.code == "partial_source"
    assert found.error.missing == ("org_id", "client_id", "scopes")
    message = str(found.error)
    assert message.startswith("No credentials found.")
    assert "environment variables has no org_id, client_id, scopes" in message
    assert "config.json has no scopes" in message
    assert found.notices == []
    assert [p.code for p in found.problems] == ["partial_source"]


def test_unknown_key_in_a_file_gives_one_debug_line(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    caplog.set_level(logging.DEBUG, logger="aa_auto_sdr.core.credentials")
    _write(tmp_path / "config.json", {**A, "sandbox": "dev", "note": "x"})
    assert _resolve(tmp_path).source == "config.json"
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("unknown_key")]
    assert lines == [f"unknown_key key=note path={tmp_path / 'config.json'} (ignored)"]


# --- file modes ------------------------------------------------------------


@posix_only
def test_config_file_readable_by_others_gives_one_warning(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path / "config.json", A, mode=0o644)
    _resolve(tmp_path)
    _resolve(tmp_path)
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert err.startswith(f"warning: {path} holds a credential and other users of this computer can read it.")
    assert f'chmod 600 "{path}"' in err


@posix_only
def test_dotenv_readable_by_others_gives_a_warning(tmp_path: Path) -> None:
    _dotenv(tmp_path, A)
    (tmp_path / ".env").chmod(0o640)
    found = _lookup(tmp_path)
    assert [w.code for w in found.warnings] == ["file_readable_by_others"]


@posix_only
def test_a_normal_run_does_not_check_files_below_the_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, value in A.items():
        monkeypatch.setenv(name.upper(), value)
    _write(tmp_path / "config.json", B, mode=0o644)
    assert _resolve(tmp_path).source == "env"
    assert capsys.readouterr().err == ""
    scanned = _lookup(tmp_path, scan_all=True)
    assert [(s.kind, s.used, s.skipped) for s in scanned.sources] == [
        ("environment", True, None),
        ("default_config", False, "lower_priority"),
    ]
    assert [w.code for w in scanned.warnings] == ["file_readable_by_others"]


def test_readable_by_others_is_false_on_windows_and_for_a_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert profiles.readable_by_others(tmp_path / "missing.json") is False
    path = _write(tmp_path / "config.json", A, mode=0o644)
    monkeypatch.setattr(os, "name", "nt")
    assert profiles.readable_by_others(path) is False


@posix_only
def test_new_profile_folders_are_private_and_existing_ones_keep_their_mode(tmp_path: Path) -> None:
    base = tmp_path / ".aa"
    base.mkdir(mode=0o755)
    base.chmod(0o755)
    path = profiles.write_profile("prod", A, base=base)
    assert base.stat().st_mode & 0o777 == 0o755
    assert (base / "orgs").stat().st_mode & 0o777 == 0o700
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600
    # Writing again replaces the file and leaves the folders as they are.
    path.parent.chmod(0o750)
    profiles.write_profile("prod", B, base=base)
    assert path.parent.stat().st_mode & 0o777 == 0o750
    assert path.stat().st_mode & 0o777 == 0o600


# --- --config --------------------------------------------------------------


def test_config_file_gives_the_credential(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write(tmp_path / "elsewhere" / "cred.json", A)
    _write(tmp_path / ".aa" / "orgs" / "other" / "config.json", B)
    monkeypatch.setenv("AA_PROFILE", "other")
    for name, value in B.items():
        monkeypatch.setenv(name.upper(), value)
    creds = _resolve(tmp_path, config=path)
    assert creds.source == f"config:{path}"
    assert creds.client_id == A["client_id"]
    found = _lookup(tmp_path, config=path)
    assert found.used is not None
    assert found.used.kind == "flag_config"
    assert found.profile is None


def test_config_path_set_for_the_run_is_used_by_every_lookup(tmp_path: Path) -> None:
    path = _write(tmp_path / "cred.json", A)
    credentials.set_config_path(str(path))
    assert _resolve(tmp_path).source == f"config:{path}"
    assert credentials.resolution_chain(working_dir=tmp_path)[0] == credentials.ResolutionEntry(
        priority=1, source=f"--config={path}", matched=True
    )
    credentials.set_config_path(None)
    with pytest.raises(ConfigError, match="No credentials found"):
        _resolve(tmp_path)


def test_config_and_profile_together_are_an_error(tmp_path: Path) -> None:
    path = _write(tmp_path / "cred.json", A)
    _write(tmp_path / ".aa" / "orgs" / "prod" / "config.json", B)
    with pytest.raises(ConfigError, match="cannot be used together") as caught:
        _resolve(tmp_path, profile="prod", config=path)
    assert caught.value.code == "profile_and_config_both_given"


def test_missing_config_file_is_an_error_with_no_fall_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in B.items():
        monkeypatch.setenv(name.upper(), value)
    with pytest.raises(ConfigError, match="--config: no file at"):
        _resolve(tmp_path, config=tmp_path / "missing.json")


def test_partial_config_file_is_an_error_that_names_the_missing_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in B.items():
        monkeypatch.setenv(name.upper(), value)
    path = _write(tmp_path / "cred.json", {k: v for k, v in A.items() if k != "secret"})
    with pytest.raises(ConfigError, match="Missing required credential fields: secret") as caught:
        _resolve(tmp_path, config=path)
    assert caught.value.code == "partial_source"
    assert caught.value.missing == ("secret",)


def test_damaged_config_file_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "cred.json"
    path.write_text("{not json", encoding="utf-8")
    found = _lookup(tmp_path, config=path)
    assert found.creds is None
    assert [p.code for p in found.problems] == ["no_credential"]
    assert "--config" in found.problems[0].message


def test_validate_only_reads_the_config_file(tmp_path: Path) -> None:
    path = _write(tmp_path / "cred.json", {**A, "org_id": "not-an-org"})
    with pytest.raises(ConfigError, match="does not match Adobe shape"):
        credentials.validate_only(config=path, working_dir=tmp_path)


# --- the config check report ----------------------------------------------


def test_scan_lists_the_sources_below_a_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path / ".aa" / "orgs" / "prod" / "config.json", A)
    monkeypatch.setenv("ORG_ID", B["org_id"])
    _dotenv(tmp_path, B)
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")
    found = _lookup(tmp_path, profile="prod", scan_all=True)
    assert found.profile == "prod"
    assert [(s.kind, s.used, s.skipped) for s in found.sources] == [
        ("flag_profile", True, None),
        ("environment", False, "lower_priority"),
        ("dotenv", False, "lower_priority"),
    ]
    assert found.notices == []
    assert [(e.source, e.matched) for e in credentials.chain_of(found, profile="prod")] == [
        ("--profile=prod", True),
        ("env vars", False),
        (".env (cwd)", False),
        ("config.json (cwd)", False),
    ]


def test_source_report_never_holds_a_value(tmp_path: Path) -> None:
    _write(tmp_path / "config.json", {**A, "sandbox": "dev"})
    found = _lookup(tmp_path, scan_all=True)
    text = json.dumps([s.as_dict() for s in found.sources])
    for value in A.values():
        assert value not in text
    assert found.sources[0].fields == ["org_id", "client_id", "secret", "scopes", "sandbox"]


def test_unreadable_dotenv_below_the_winner_gives_no_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in A.items():
        monkeypatch.setenv(name.upper(), value)
    (tmp_path / ".env").write_bytes(b"ORG_ID=\xff\xfe\n")
    found = _lookup(tmp_path, scan_all=True)
    assert found.warnings == []
    assert [s.kind for s in found.sources] == ["environment"]


# --- profile names ---------------------------------------------------------


@pytest.mark.parametrize("name", ["../other", "..", "", "a/b", "a\\b", "/etc/passwd", ".hidden", "my profile"])
def test_invalid_profile_name_is_refused_on_read_before_any_file_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    opened: list[object] = []

    def record(path: Path, label: str) -> dict[str, object]:
        opened.append(path)
        return {}

    monkeypatch.setattr(profiles, "read_config_object", record)
    with pytest.raises(ConfigError) as caught:
        profiles.read_profile(name, base=tmp_path / ".aa")
    assert caught.value.code == "invalid_profile_name"
    assert opened == []
    found = _lookup(tmp_path, profile=name) if name else None
    if found is not None:
        assert found.error is not None
        assert found.error.code == "invalid_profile_name"


def test_name_outside_the_profiles_folder_is_refused_even_when_a_file_is_there(tmp_path: Path) -> None:
    _write(tmp_path / ".aa" / "other" / "config.json", A)
    with pytest.raises(ConfigError, match="invalid profile name"):
        _resolve(tmp_path, profile="../other")


@pytest.mark.parametrize("name", ["my profile", ".hidden", "-x", "kunde-münchen"])
def test_existing_profile_with_an_old_style_name_still_works_with_one_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    _write(tmp_path / ".aa" / "orgs" / name / "config.json", A)
    creds = _resolve(tmp_path, profile=name)
    assert creds.source == f"profile:{name}"
    assert profiles.read_profile(name, base=tmp_path / ".aa")["client_id"] == A["client_id"]
    profiles.write_profile(name, B, base=tmp_path / ".aa")
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert err.startswith(f"warning: profile name '{name}' breaks the profile name rule")


@pytest.mark.parametrize("name", ["my profile", ".hidden", "a" * 65])
def test_new_profile_with_an_invalid_name_is_not_written(tmp_path: Path, name: str) -> None:
    with pytest.raises(ConfigError, match="invalid profile name"):
        profiles.write_profile(name, A, base=tmp_path / ".aa")
    assert not (tmp_path / ".aa").exists()


def test_profile_error_codes(tmp_path: Path) -> None:
    found = _lookup(tmp_path, profile="missing")
    assert found.profile == "missing"
    assert [p.code for p in found.problems] == ["profile_not_found"]
    with pytest.raises(ConfigError) as caught:
        profiles.read_profile("missing", base=tmp_path / ".aa")
    assert caught.value.code == "profile_not_found"


# --- masking ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("client_id", "shown"),
    [
        ("aaaa1111bbbb2222cccc3333dddd4444", "aaaa****4444"),
        ("abcdefghi", "abcd****fghi"),
        ("abcdefgh", "****"),
        ("", "****"),
    ],
)
def test_mask_client_id(client_id: str, shown: str) -> None:
    assert credentials.mask_client_id(client_id) == shown


def test_mask_secret_never_shows_a_character_or_the_length() -> None:
    assert credentials.mask_secret("abc") == credentials.mask_secret("a" * 80) == "****"
    assert credentials.mask_secret("") == ""


def test_shown_credential_holds_no_secret() -> None:
    creds = credentials.Credentials(
        org_id="A1B2C3D4E5F6A7B8C9D0E1F2@AdobeOrg",
        client_id="aaaa1111bbbb2222cccc3333dddd4444",
        secret="fake-secret-A-not-a-credential-0001",
        scopes="openid,AdobeID",
        source="env",
    )
    shown = creds.shown()
    assert shown == credentials.ShownCredential(
        source="env",
        org_id="A1B2C3D4E5F6A7B8C9D0E1F2@AdobeOrg",
        client_id="aaaa****4444",
        secret="****",
        scopes="openid,AdobeID",
    )
    assert creds.secret not in repr(shown)
