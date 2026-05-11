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


class TestBatchModeGit:
    def test_batch_threads_git_flags_to_each_rsid(self, tmp_path: Path) -> None:
        """Each RSID in --batch passes through git_commit/git_push/git_message
        to run_single. Per-RSID commit failures isolate (one fail doesn't
        abort the batch)."""
        from aa_auto_sdr.pipeline import batch as batch_mod
        from aa_auto_sdr.pipeline.models import RunResult

        rsid_results = {
            "rs_a": RunResult(
                rsid="rs_a",
                success=True,
                git_op=GitOpResult(ok=True, committed=True, commit_sha="a" * 40),
            ),
            "rs_b": RunResult(
                rsid="rs_b",
                success=True,
                git_op=GitOpResult(
                    ok=False,
                    committed=True,
                    error_kind="GitPushError",
                    error_message="remote rejected",
                ),
            ),
        }

        captured_kwargs: list[dict] = []

        def fake_run_single(**kwargs):
            captured_kwargs.append(kwargs)
            return rsid_results[kwargs["rsid"]]

        with patch.object(batch_mod, "run_single", side_effect=fake_run_single):
            result = batch_mod.run_batch(
                client=_fake_client(),
                rsids=["rs_a", "rs_b"],
                formats=["json"],
                output_dir=tmp_path,
                captured_at=_now_utc(),
                tool_version="1.15.0",
                snapshot_dir=tmp_path,
                git_commit=True,
                git_push=True,
                git_message=None,
            )

        assert len(captured_kwargs) == 2
        for kw in captured_kwargs:
            assert kw["git_commit"] is True
            assert kw["git_push"] is True
            assert kw["git_message"] is None
        assert len(result.successes) == 2
        assert result.successes[1].git_op.ok is False


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
