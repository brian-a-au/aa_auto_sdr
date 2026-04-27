"""v1.2 config introspection: --config-status, --validate-config, --sample-config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_auto_sdr.cli.commands import config as cmd
from aa_auto_sdr.core.exit_codes import ExitCode


class TestSampleConfig:
    def test_emits_template_to_stdout(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = cmd.sample_config()
        assert rc == ExitCode.OK.value
        out = capsys.readouterr().out
        # The output is parseable JSON and contains the four required keys.
        data = json.loads(out)
        assert {"org_id", "client_id", "secret", "scopes"} <= data.keys()


class TestValidateConfig:
    def test_valid_credentials_pass(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("ORG_ID", "abc@AdobeOrg")
        monkeypatch.setenv("CLIENT_ID", "abcdefghijkl")
        monkeypatch.setenv("SECRET", "topsecret")
        monkeypatch.setenv("SCOPES", "openid AdobeID")
        monkeypatch.chdir(tmp_path)
        rc = cmd.validate_config(profile=None)
        assert rc == ExitCode.OK.value

    def test_malformed_org_id(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("ORG_ID", "not-an-org-id")
        monkeypatch.setenv("CLIENT_ID", "abcdefgh")
        monkeypatch.setenv("SECRET", "x")
        monkeypatch.setenv("SCOPES", "openid")
        monkeypatch.chdir(tmp_path)
        rc = cmd.validate_config(profile=None)
        assert rc == ExitCode.CONFIG.value
        assert "AdobeOrg" in capsys.readouterr().out

    def test_missing_field(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
            monkeypatch.delenv(v, raising=False)
        monkeypatch.chdir(tmp_path)
        rc = cmd.validate_config(profile=None)
        assert rc == ExitCode.CONFIG.value


class TestConfigStatus:
    def test_prints_resolution_chain(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("ORG_ID", "abc@AdobeOrg")
        monkeypatch.setenv("CLIENT_ID", "abcdefgh")
        monkeypatch.setenv("SECRET", "x")
        monkeypatch.setenv("SCOPES", "openid")
        monkeypatch.chdir(tmp_path)
        rc = cmd.config_status(profile=None)
        assert rc == ExitCode.OK.value
        out = capsys.readouterr().out
        # Resolution chain mentions env-vars source
        assert "env" in out.lower()
        assert "Resolved" in out or "resolved" in out

    def test_chain_when_no_creds(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
            monkeypatch.delenv(v, raising=False)
        monkeypatch.chdir(tmp_path)
        rc = cmd.config_status(profile=None)
        # Chain prints, but resolve() fails → CONFIG
        assert rc == ExitCode.CONFIG.value
        out = capsys.readouterr().out
        assert "Resolution chain" in out
