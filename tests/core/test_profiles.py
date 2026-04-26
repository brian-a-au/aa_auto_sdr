"""Profile CRUD tests. ~/.aa/orgs/<name>/config.json layout."""

import json
from pathlib import Path

import pytest

from aa_auto_sdr.core import profiles
from aa_auto_sdr.core.exceptions import ConfigError


def test_read_profile_returns_dict_when_present(tmp_path: Path) -> None:
    profile_dir = tmp_path / "orgs" / "test"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.json").write_text(
        json.dumps(
            {
                "org_id": "O",
                "client_id": "C",
                "secret": "S",
                "scopes": "X",
            }
        )
    )
    result = profiles.read_profile("test", base=tmp_path)
    assert result["org_id"] == "O"


def test_read_profile_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc_info:
        profiles.read_profile("missing", base=tmp_path)
    assert "missing" in str(exc_info.value)


def test_write_profile_creates_dir_and_file(tmp_path: Path) -> None:
    profiles.write_profile("p", {"org_id": "O"}, base=tmp_path)
    assert (tmp_path / "orgs" / "p" / "config.json").exists()


def test_default_base_is_home_aa(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert profiles.default_base() == tmp_path / ".aa"


def test_list_profiles_returns_sorted_names(tmp_path: Path) -> None:
    for name in ("zeta", "alpha", "mid"):
        profiles.write_profile(name, {"org_id": "O"}, base=tmp_path)
    assert profiles.list_profiles(base=tmp_path) == ["alpha", "mid", "zeta"]


def test_list_profiles_empty_when_no_dir(tmp_path: Path) -> None:
    assert profiles.list_profiles(base=tmp_path) == []
