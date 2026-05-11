"""Pipeline composition with git ops (single / batch / watch)."""

from __future__ import annotations

import argparse  # noqa: F401
from dataclasses import dataclass, field
from datetime import timedelta  # noqa: F401
from pathlib import Path
from typing import Any  # noqa: F401
from unittest.mock import MagicMock, patch

import pytest  # noqa: F401

from aa_auto_sdr.snapshot.git import GitOpResult


class TestSingleModeGit:
    def test_run_single_returns_git_op_when_git_commit_true(self, tmp_path: Path) -> None:
        from aa_auto_sdr.pipeline import single as single_mod

        fake_doc = _fake_sdr_doc(rsid="rs_a")
        fake_path = tmp_path / "rs_a" / "snap.json"
        fake_path.parent.mkdir(parents=True)
        fake_path.write_text("{}")

        fake_writer = MagicMock()
        fake_writer.extension = ".json"
        fake_writer.write.return_value = [tmp_path / "out" / "rs_a.json"]

        with (
            patch.object(single_mod, "build_sdr", return_value=fake_doc),
            patch.object(single_mod.registry, "get_writer", return_value=fake_writer),
            patch.object(single_mod.registry, "bootstrap"),
            patch("aa_auto_sdr.snapshot.store.save_snapshot", return_value=fake_path),
            patch(
                "aa_auto_sdr.snapshot.git.git_commit_snapshot",
                return_value=GitOpResult(
                    ok=True,
                    committed=True,
                    pushed=False,
                    commit_sha="abc1234567abc1234567abc1234567abc1234567",
                ),
            ) as mock_commit,
        ):
            result = single_mod.run_single(
                client=_fake_client(),
                rsid="rs_a",
                formats=["json"],
                output_dir=tmp_path / "out",
                captured_at=_now_utc(),
                tool_version="1.15.0",
                snapshot_dir=tmp_path,
                git_commit=True,
                git_push=False,
                git_message=None,
            )

        assert result.success is True
        assert result.git_op is not None
        assert result.git_op.ok is True
        assert result.git_op.committed is True
        assert result.git_op.commit_sha is not None
        assert len(result.git_op.commit_sha) == 40
        mock_commit.assert_called_once()

    def test_run_single_no_git_op_when_git_commit_false(self, tmp_path: Path) -> None:
        from aa_auto_sdr.pipeline import single as single_mod

        fake_writer2 = MagicMock()
        fake_writer2.extension = ".json"
        fake_writer2.write.return_value = [tmp_path / "out" / "rs_a.json"]

        with (
            patch.object(single_mod, "build_sdr", return_value=_fake_sdr_doc(rsid="rs_a")),
            patch.object(single_mod.registry, "get_writer", return_value=fake_writer2),
            patch.object(single_mod.registry, "bootstrap"),
            patch("aa_auto_sdr.snapshot.store.save_snapshot", return_value=tmp_path / "snap.json"),
            patch("aa_auto_sdr.snapshot.git.git_commit_snapshot") as mock_commit,
        ):
            result = single_mod.run_single(
                client=_fake_client(),
                rsid="rs_a",
                formats=["json"],
                output_dir=tmp_path / "out",
                captured_at=_now_utc(),
                tool_version="1.15.0",
                snapshot_dir=tmp_path,
                git_commit=False,
            )

        assert result.git_op is None
        mock_commit.assert_not_called()


# --- helpers ---


def _now_utc():
    from datetime import UTC, datetime

    return datetime.now(UTC)


def _fake_client():
    return object()


def _fake_sdr_doc(*, rsid: str):
    @dataclass
    class _RS:
        name: str = "test"

    @dataclass
    class _Doc:
        report_suite: _RS = field(default_factory=_RS)
        quality: dict | None = None

        def to_dict(self) -> dict:
            return {"report_suite": {"name": self.report_suite.name}}

    return _Doc()
