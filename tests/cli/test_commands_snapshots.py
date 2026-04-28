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


@pytest.fixture
def aa_home_multi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Same as aa_home but with two RSIDs (RS1, RS2) so rsid= filter is exercised."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    aa = home / ".aa"
    for rsid in ("RS1", "RS2"):
        rs_dir = aa / "orgs" / "prod" / "snapshots" / rsid
        rs_dir.mkdir(parents=True)
        for day in ("25", "26"):
            _touch(rs_dir / f"2026-04-{day}T10-00-00+00-00.json")
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
        # captured_at should be canonical ISO-8601 (with colons), not the filename stem.
        assert rows[0]["captured_at"] == "2026-04-25T10:00:00+00:00"
        assert rows[1]["captured_at"] == "2026-04-26T10:00:00+00:00"

    def test_rsid_filter(self, aa_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.list_run(profile="prod", rsid="RS_OTHER", format_name="json")
        assert rc == ExitCode.OK.value
        assert json.loads(capsys.readouterr().out) == []

    def test_rsid_filter_narrows_to_one_rsid(
        self,
        aa_home_multi: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = cmd.list_run(profile="prod", rsid="RS1", format_name="json")
        assert rc == ExitCode.OK.value
        rows = json.loads(capsys.readouterr().out)
        assert len(rows) == 2
        assert all(r["rsid"] == "RS1" for r in rows)

    def test_bad_format(self, aa_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cmd.list_run(profile="prod", rsid=None, format_name="yaml")
        assert rc == ExitCode.OUTPUT.value
        assert "json|table" in capsys.readouterr().out

    def test_table_format_empty(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Empty profile dir should print '(no snapshots)' under table format."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        (home / ".aa" / "orgs" / "prod" / "snapshots").mkdir(parents=True)
        rc = cmd.list_run(profile="prod", rsid=None, format_name="table")
        assert rc == ExitCode.OK.value
        assert "(no snapshots)" in capsys.readouterr().out


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
            assume_yes=True,  # v1.2: confirmation gate
        )
        assert rc == ExitCode.OK.value
        rs_dir = aa_home / "orgs" / "prod" / "snapshots" / "RS1"
        assert len(list(rs_dir.glob("*.json"))) == 1

    def test_prune_filtered_to_one_rsid_leaves_others(
        self,
        aa_home_multi: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = cmd.prune_run(
            profile="prod",
            rsid="RS1",
            keep_last=1,
            keep_since=None,
            dry_run=False,
            assume_yes=True,  # v1.2: confirmation gate
        )
        assert rc == ExitCode.OK.value
        rs1_dir = aa_home_multi / "orgs" / "prod" / "snapshots" / "RS1"
        rs2_dir = aa_home_multi / "orgs" / "prod" / "snapshots" / "RS2"
        assert len(list(rs1_dir.glob("*.json"))) == 1  # pruned to 1
        assert len(list(rs2_dir.glob("*.json"))) == 2  # untouched

    def test_prune_zero_deletions_message(
        self,
        aa_home: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When policy keeps everything, prune reports '0 snapshots'.

        Zero-delete path skips the confirmation prompt entirely (no files would
        be removed), so `assume_yes` is irrelevant here."""
        rc = cmd.prune_run(
            profile="prod",
            rsid=None,
            keep_last=999,  # higher than fixture count → no deletions
            keep_since=None,
            dry_run=False,
        )
        assert rc == ExitCode.OK.value
        assert "deleted: 0 snapshots" in capsys.readouterr().out


class TestPruneConfirmation:
    """v1.2 confirmation gate; v1.2.1 changes refusal exit code OK → USAGE."""

    def test_prune_aborts_on_non_tty_without_assume_yes_returns_usage(
        self,
        aa_home: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """v1.2.1: --prune-snapshots without --yes on non-tty stdin → USAGE (2),
        no delete. Was OK (0) in v1.2.0 — breaking change for CI scripts."""
        rc = cmd.prune_run(
            profile="prod",
            rsid=None,
            keep_last=1,
            keep_since=None,
            dry_run=False,
            assume_yes=False,
        )
        assert rc == ExitCode.USAGE.value
        out = capsys.readouterr().out
        assert "aborted" in out
        assert "non-interactive" in out  # new wording
        assert "--yes" in out  # new wording references the flag
        # Files NOT deleted
        rs_dir = aa_home / "orgs" / "prod" / "snapshots" / "RS1"
        assert len(list(rs_dir.glob("*.json"))) == 2
