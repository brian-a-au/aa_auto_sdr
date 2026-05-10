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
            total_available=10,
        )
        # The banner reads strategy from result via a separate field if added,
        # OR infers from the absence-of-strategy. v1.10.0 spec keeps strategy on
        # the log line only and renders banner from a heuristic on sample_seed.
        # If `sample_strategy` is added to BatchResult later, update this test.
        buf = StringIO()
        with patch("sys.stdout", buf):
            _print_summary(result)
        out = buf.getvalue()
        # Random by default; stratified surface deferred unless sample_strategy
        # field is added. Assert the seeded random banner format here.
        assert "Sampled 3 of 10 RSIDs" in out
        assert "seed=7" in out
