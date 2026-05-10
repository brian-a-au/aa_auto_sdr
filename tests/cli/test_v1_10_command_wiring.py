"""Banner + command-wiring tests (v1.10.0)."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from aa_auto_sdr.cli.commands.batch import _print_summary
from aa_auto_sdr.pipeline.models import BatchResult


class TestBannerSampling:
    def test_unsampled_banner_omits_sampled_line(self) -> None:
        result = BatchResult(
            successes=[],
            failures=[],
            total_duration_seconds=0.0,
            total_output_bytes=0,
            batch_id="test",
            sampled=False,
            total_available=10,
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_summary(result)
        out = buf.getvalue()
        assert "Sampled" not in out

    def test_sampled_banner_with_seed(self) -> None:
        result = BatchResult(
            successes=[],
            failures=[],
            total_duration_seconds=0.0,
            total_output_bytes=0,
            batch_id="test",
            sampled=True,
            sample_size=3,
            sample_seed=42,
            total_available=10,
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_summary(result)
        out = buf.getvalue()
        assert "Sampled 3 of 10 RSIDs" in out
        assert "seed=42" in out
        assert "strategy=random" in out

    def test_sampled_banner_without_seed(self) -> None:
        result = BatchResult(
            successes=[],
            failures=[],
            total_duration_seconds=0.0,
            total_output_bytes=0,
            batch_id="test",
            sampled=True,
            sample_size=3,
            sample_seed=None,
            total_available=10,
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_summary(result)
        out = buf.getvalue()
        assert "Sampled 3 of 10 RSIDs" in out
        assert "seed=" not in out
        assert "strategy=random" in out

    def test_sampled_banner_stratified_strategy(self) -> None:
        result = BatchResult(
            successes=[],
            failures=[],
            total_duration_seconds=0.0,
            total_output_bytes=0,
            batch_id="test",
            sampled=True,
            sample_size=3,
            sample_seed=7,
            sample_strategy="stratified",
            total_available=10,
        )
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_summary(result)
        out = buf.getvalue()
        assert "Sampled 3 of 10 RSIDs" in out
        assert "seed=7" in out
        assert "strategy=stratified" in out
