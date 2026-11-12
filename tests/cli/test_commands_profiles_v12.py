"""v1.2 profile commands: --profile-overwrite gate on import."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_auto_sdr.cli.commands import profiles as cmd
from aa_auto_sdr.core.exit_codes import ExitCode


@pytest.fixture
def aa_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / ".aa"
    (base / "orgs").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    return base


def _make_creds_file(tmp_path: Path) -> Path:
    src = tmp_path / "creds.json"
    src.write_text(
        json.dumps(
            {
                "org_id": "x@AdobeOrg",
                "client_id": "12345678abcdefgh",
                "secret": "topsecret",
                "scopes": "openid",
            },
        ),
    )
    return src


class TestProfileOverwrite:
    def test_import_against_existing_errors_without_overwrite(
        self,
        aa_base: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        src = _make_creds_file(tmp_path)
        rc1 = cmd.import_run("prod", str(src), base=aa_base)
        assert rc1 == ExitCode.OK.value
        rc2 = cmd.import_run("prod", str(src), base=aa_base)
        assert rc2 == ExitCode.CONFIG.value
        err = capsys.readouterr().err
        assert "already exists" in err
        assert "--profile-overwrite" in err

    def test_import_with_overwrite_succeeds(
        self,
        aa_base: Path,
        tmp_path: Path,
    ) -> None:
        src = _make_creds_file(tmp_path)
        cmd.import_run("prod", str(src), base=aa_base)
        src.write_text(
            json.dumps(
                {
                    "org_id": "y@AdobeOrg",
                    "client_id": "abcdefgh87654321",
                    "secret": "newsecret",
                    "scopes": "openid",
                },
            ),
        )
        rc = cmd.import_run("prod", str(src), base=aa_base, overwrite=True)
        assert rc == ExitCode.OK.value
        with (aa_base / "orgs" / "prod" / "config.json").open() as fh:
            data = json.load(fh)
        assert data["org_id"] == "y@AdobeOrg"

    def test_import_first_time_unchanged(
        self,
        aa_base: Path,
        tmp_path: Path,
    ) -> None:
        """Default behavior on a fresh profile name still works without --profile-overwrite."""
        src = _make_creds_file(tmp_path)
        rc = cmd.import_run("fresh", str(src), base=aa_base)
        assert rc == ExitCode.OK.value

    def test_import_succeeds_when_dir_has_only_snapshots(
        self,
        aa_base: Path,
        tmp_path: Path,
    ) -> None:
        """A snapshot run with no --profile creates orgs/default/snapshots/ but no
        config.json. That folder is not a profile, so import needs no overwrite flag."""
        (aa_base / "orgs" / "default" / "snapshots").mkdir(parents=True)
        src = _make_creds_file(tmp_path)
        rc = cmd.import_run("default", str(src), base=aa_base)
        assert rc == ExitCode.OK.value
        assert (aa_base / "orgs" / "default" / "config.json").exists()
        assert (aa_base / "orgs" / "default" / "snapshots").is_dir()

    def test_import_still_refuses_when_target_is_a_file(self, aa_base: Path, tmp_path: Path, capsys) -> None:
        """orgs/<name> as a plain file is refused with CONFIG, not a traceback."""
        (aa_base / "orgs" / "f").write_text("not a profile", encoding="utf-8")
        rc = cmd.import_run("f", str(_make_creds_file(tmp_path)), base=aa_base)
        assert rc == ExitCode.CONFIG.value
        assert "already exists" in capsys.readouterr().err
        assert (aa_base / "orgs" / "f").read_text(encoding="utf-8") == "not a profile"

    @pytest.mark.parametrize("name", ["..", ".", ""])
    def test_import_still_refuses_dot_names(self, aa_base: Path, tmp_path: Path, name: str) -> None:
        """Names that resolve to orgs/ or its parent were always refused; the
        snapshot-only allowance must not open them up."""
        rc = cmd.import_run(name, str(_make_creds_file(tmp_path)), base=aa_base)
        assert rc == ExitCode.CONFIG.value
        assert not (aa_base / "config.json").exists()
        assert not (aa_base / "orgs" / "config.json").exists()

    @pytest.mark.parametrize("name", ["", ".", "..", "../../escape", "a/b", "a\\b"])
    def test_import_rejects_an_unsafe_name(
        self, aa_base: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
    ) -> None:
        """--profile-import uses the same name check as --profile-add: exit 10,
        an "invalid profile name" error, and nothing written, even with
        --profile-overwrite."""
        src = _make_creds_file(tmp_path)
        rc = cmd.import_run(name, str(src), base=aa_base, overwrite=True)
        assert rc == ExitCode.CONFIG.value
        assert f"error: invalid profile name '{name}'" in capsys.readouterr().err
        assert sorted(p for p in tmp_path.rglob("config.json")) == []

    def test_import_still_refuses_dangling_config_symlink(self, aa_base: Path, tmp_path: Path) -> None:
        target_dir = aa_base / "orgs" / "linked"
        target_dir.mkdir(parents=True)
        try:
            (target_dir / "config.json").symlink_to(tmp_path / "missing.json")
        except OSError:
            pytest.skip("symlinks not available")
        rc = cmd.import_run("linked", str(_make_creds_file(tmp_path)), base=aa_base)
        assert rc == ExitCode.CONFIG.value
        assert (target_dir / "config.json").is_symlink()
