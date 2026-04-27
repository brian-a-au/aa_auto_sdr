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
        out = capsys.readouterr().out
        assert "already exists" in out
        assert "--profile-overwrite" in out

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
