"""--profile-list / --profile-test / --profile-show / --profile-import handlers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_auto_sdr.cli.commands import profiles as cmd
from aa_auto_sdr.core.exceptions import AuthError
from aa_auto_sdr.core.exit_codes import ExitCode


@pytest.fixture
def aa_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / ".aa"
    (base / "orgs").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    return base


def _seed_profile(base: Path, name: str, **fields: str) -> None:
    pdir = base / "orgs" / name
    pdir.mkdir(parents=True)
    data = {
        "org_id": "abc@AdobeOrg",
        "client_id": "abcdefgh12345678",
        "secret": "supersecret",
        "scopes": "openid",
        "sandbox": None,
        **fields,
    }
    (pdir / "config.json").write_text(json.dumps(data))


class TestProfileList:
    def test_empty(self, aa_base: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.list_run(format_name="json", base=aa_base)
        assert rc == ExitCode.OK.value
        assert json.loads(capsys.readouterr().out) == []

    def test_table_with_two_profiles(
        self,
        aa_base: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _seed_profile(aa_base, "prod")
        _seed_profile(aa_base, "stage")
        rc = cmd.list_run(format_name="table", base=aa_base)
        assert rc == ExitCode.OK.value
        out = capsys.readouterr().out
        assert "prod" in out
        assert "stage" in out

    def test_bad_format(self, aa_base: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.list_run(format_name="yaml", base=aa_base)
        assert rc == ExitCode.OUTPUT.value


class TestProfileShow:
    def test_show_masks_client_id(
        self,
        aa_base: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _seed_profile(aa_base, "prod")
        rc = cmd.show_run("prod", base=aa_base)
        assert rc == ExitCode.OK.value
        out = capsys.readouterr().out
        assert "abcd…5678" in out
        assert "supersecret" not in out

    def test_missing_profile(
        self,
        aa_base: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = cmd.show_run("nope", base=aa_base)
        assert rc == ExitCode.CONFIG.value


class TestProfileImport:
    def test_round_trip(self, aa_base: Path, tmp_path: Path) -> None:
        src = tmp_path / "creds.json"
        src.write_text(
            json.dumps(
                {
                    "org_id": "x@AdobeOrg",
                    "client_id": "12345678abcdefgh",
                    "secret": "topsecret",
                    "scopes": "openid",
                }
            )
        )
        rc = cmd.import_run("imported", str(src), base=aa_base)
        assert rc == ExitCode.OK.value
        assert (aa_base / "orgs" / "imported" / "config.json").exists()

    def test_missing_required_fields(
        self,
        aa_base: Path,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        src = tmp_path / "bad.json"
        src.write_text(json.dumps({"org_id": "x"}))
        rc = cmd.import_run("bad", str(src), base=aa_base)
        assert rc == ExitCode.CONFIG.value
        assert "missing required" in capsys.readouterr().out

    def test_file_not_found(
        self,
        aa_base: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = cmd.import_run("x", "/no/such/path.json", base=aa_base)
        assert rc == ExitCode.CONFIG.value


class TestProfileTest:
    def test_pass(
        self,
        aa_base: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _seed_profile(aa_base, "prod")
        from aa_auto_sdr.api import client as api_client

        class _StubClient:
            company_id = "TEST_COMPANY"

        def _stub_from_credentials(cls, creds, *, company_id=None):
            return _StubClient()

        monkeypatch.setattr(
            api_client.AaClient,
            "from_credentials",
            classmethod(_stub_from_credentials),
        )
        rc = cmd.test_run("prod", base=aa_base)
        assert rc == ExitCode.OK.value
        assert "PASS" in capsys.readouterr().out

    def test_auth_failure(
        self,
        aa_base: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _seed_profile(aa_base, "prod")
        from aa_auto_sdr.api import client as api_client

        def _raise(cls, creds, *, company_id=None):
            raise AuthError("bad creds")

        monkeypatch.setattr(
            api_client.AaClient,
            "from_credentials",
            classmethod(_raise),
        )
        rc = cmd.test_run("prod", base=aa_base)
        assert rc == ExitCode.AUTH.value
        assert "FAIL" in capsys.readouterr().out

    def test_config_failure(
        self,
        aa_base: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = cmd.test_run("missing-profile", base=aa_base)
        assert rc == ExitCode.CONFIG.value
