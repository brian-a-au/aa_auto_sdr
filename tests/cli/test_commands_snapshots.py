"""--list-snapshots and --prune-snapshots handler tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_auto_sdr.cli.commands import snapshots as cmd
from aa_auto_sdr.core.exit_codes import ExitCode


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    return path


@pytest.fixture
def aa_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect `~/.aa` to a tmp dir."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    aa = home / ".aa"
    (aa / "orgs" / "prod" / "snapshots" / "RS1").mkdir(parents=True)
    _touch(aa / "orgs" / "prod" / "snapshots" / "RS1" / "2026-04-25T10-00-00+00-00.json")
    _touch(aa / "orgs" / "prod" / "snapshots" / "RS1" / "2026-04-26T10-00-00+00-00.json")
    return aa


class TestListSnapshots:
    def test_requires_profile(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.list_run(profile=None, rsid=None, format_name=None)
        assert rc == ExitCode.CONFIG.value
        assert "requires --profile" in capsys.readouterr().out

    def test_table_format(self, aa_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.list_run(profile="prod", rsid=None, format_name="table")
        assert rc == ExitCode.OK.value
        out = capsys.readouterr().out
        assert "RSID" in out
        assert "RS1" in out

    def test_json_format(self, aa_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.list_run(profile="prod", rsid=None, format_name="json")
        assert rc == ExitCode.OK.value
        rows = json.loads(capsys.readouterr().out)
        assert len(rows) == 2
        assert rows[0]["rsid"] == "RS1"

    def test_rsid_filter(self, aa_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.list_run(profile="prod", rsid="RS_OTHER", format_name="json")
        assert rc == ExitCode.OK.value
        assert json.loads(capsys.readouterr().out) == []

    def test_bad_format(self, aa_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.list_run(profile="prod", rsid=None, format_name="yaml")
        assert rc == ExitCode.OUTPUT.value


class TestPruneSnapshots:
    def test_requires_profile(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.prune_run(
            profile=None,
            rsid=None,
            keep_last=5,
            keep_since=None,
            dry_run=False,
        )
        assert rc == ExitCode.CONFIG.value

    def test_requires_policy(self, aa_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.prune_run(
            profile="prod",
            rsid=None,
            keep_last=None,
            keep_since=None,
            dry_run=False,
        )
        assert rc == ExitCode.CONFIG.value

    def test_bad_keep_since_format(self, aa_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.prune_run(
            profile="prod",
            rsid=None,
            keep_last=None,
            keep_since="forever",
            dry_run=False,
        )
        assert rc == ExitCode.CONFIG.value

    def test_dry_run_keeps_files(self, aa_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.prune_run(
            profile="prod",
            rsid=None,
            keep_last=1,
            keep_since=None,
            dry_run=True,
        )
        assert rc == ExitCode.OK.value
        out = capsys.readouterr().out
        assert "would delete" in out
        # File still on disk
        rs_dir = aa_home / "orgs" / "prod" / "snapshots" / "RS1"
        assert len(list(rs_dir.glob("*.json"))) == 2

    def test_actual_delete(self, aa_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.prune_run(
            profile="prod",
            rsid=None,
            keep_last=1,
            keep_since=None,
            dry_run=False,
        )
        assert rc == ExitCode.OK.value
        rs_dir = aa_home / "orgs" / "prod" / "snapshots" / "RS1"
        assert len(list(rs_dir.glob("*.json"))) == 1
