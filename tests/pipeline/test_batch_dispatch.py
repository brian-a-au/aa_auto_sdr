"""run_batch dispatches to sequential vs parallel based on workers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.api.cache import ValidationCache
from aa_auto_sdr.pipeline.batch import run_batch


def test_workers_1_dispatches_to_sequential() -> None:
    """Default workers=1 path stays on the existing sequential implementation."""
    with (
        patch("aa_auto_sdr.pipeline.batch._run_sequential") as seq,
        patch("aa_auto_sdr.pipeline.batch.run_parallel") as par,
    ):
        seq.return_value = MagicMock(successes=[], failures=[], total_duration_seconds=0.0, total_output_bytes=0)
        run_batch(
            client=MagicMock(),
            rsids=["r1"],
            formats=["json"],
            output_dir=Path("/tmp"),
            captured_at=datetime(2026, 4, 25, tzinfo=UTC),
            tool_version="1.8.0",
            workers=1,
        )
        seq.assert_called_once()
        par.assert_not_called()


def test_workers_2_dispatches_to_parallel() -> None:
    with (
        patch("aa_auto_sdr.pipeline.batch._run_sequential") as seq,
        patch("aa_auto_sdr.pipeline.batch.run_parallel") as par,
    ):
        par.return_value = MagicMock(successes=[], failures=[], total_duration_seconds=0.0, total_output_bytes=0)
        run_batch(
            client=MagicMock(),
            rsids=["r1", "r2"],
            formats=["json"],
            output_dir=Path("/tmp"),
            captured_at=datetime(2026, 4, 25, tzinfo=UTC),
            tool_version="1.8.0",
            workers=2,
        )
        par.assert_called_once()
        seq.assert_not_called()


def test_workers_default_is_1() -> None:
    """Backward compatibility: omitting workers preserves sequential behavior."""
    with (
        patch("aa_auto_sdr.pipeline.batch._run_sequential") as seq,
        patch("aa_auto_sdr.pipeline.batch.run_parallel") as par,
    ):
        seq.return_value = MagicMock(successes=[], failures=[], total_duration_seconds=0.0, total_output_bytes=0)
        run_batch(
            client=MagicMock(),
            rsids=["r1"],
            formats=["json"],
            output_dir=Path("/tmp"),
            captured_at=datetime(2026, 4, 25, tzinfo=UTC),
            tool_version="1.8.0",
        )
        seq.assert_called_once()
        par.assert_not_called()


def test_fail_fast_threaded_through_to_run_parallel() -> None:
    with patch("aa_auto_sdr.pipeline.batch.run_parallel") as par:
        par.return_value = MagicMock(successes=[], failures=[], total_duration_seconds=0.0, total_output_bytes=0)
        run_batch(
            client=MagicMock(),
            rsids=["r1", "r2"],
            formats=["json"],
            output_dir=Path("/tmp"),
            captured_at=datetime(2026, 4, 25, tzinfo=UTC),
            tool_version="1.8.0",
            workers=2,
            fail_fast=True,
        )
        kwargs = par.call_args.kwargs
        assert kwargs["fail_fast"] is True


def test_cache_passed_through_to_run_parallel() -> None:
    cache = ValidationCache()
    with patch("aa_auto_sdr.pipeline.batch.run_parallel") as par:
        par.return_value = MagicMock(successes=[], failures=[], total_duration_seconds=0.0, total_output_bytes=0)
        run_batch(
            client=MagicMock(),
            rsids=["r1", "r2"],
            formats=["json"],
            output_dir=Path("/tmp"),
            captured_at=datetime(2026, 4, 25, tzinfo=UTC),
            tool_version="1.8.0",
            workers=2,
            cache=cache,
        )
        kwargs = par.call_args.kwargs
        assert kwargs["cache"] is cache


def test_invalid_workers_raises() -> None:
    """workers=0 or negative is rejected at dispatch time."""
    with pytest.raises(ValueError, match="workers must be >= 1"):
        run_batch(
            client=MagicMock(),
            rsids=["r1"],
            formats=["json"],
            output_dir=Path("/tmp"),
            captured_at=datetime(2026, 4, 25, tzinfo=UTC),
            tool_version="1.8.0",
            workers=0,
        )
