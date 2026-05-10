"""CLI argparse + mode-scoping for v1.10.0 sampling flags."""

from __future__ import annotations

import pytest

from aa_auto_sdr.cli.parser import build_parser
from aa_auto_sdr.core.exit_codes import ExitCode


class TestSamplingArgparse:
    def test_sample_int_value(self) -> None:
        ns = build_parser().parse_args(["--batch", "rs1", "rs2", "--sample", "5"])
        assert ns.sample_size == 5

    def test_sample_seed_int_value(self) -> None:
        ns = build_parser().parse_args(["--batch", "rs1", "rs2", "--sample", "5", "--sample-seed", "42"])
        assert ns.sample_seed == 42

    def test_sample_stratified_flag(self) -> None:
        ns = build_parser().parse_args(["--batch", "rs1", "rs2", "--sample", "5", "--sample-stratified"])
        assert ns.sample_stratified is True

    def test_sample_defaults(self) -> None:
        ns = build_parser().parse_args(["rs1"])
        assert ns.sample_size is None
        assert ns.sample_seed is None
        assert ns.sample_stratified is False


class TestDroppedFlagsRejected:
    def test_memory_limit_rejected(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--batch", "rs1", "--memory-limit", "100"])

    def test_memory_warning_rejected(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--batch", "rs1", "--memory-warning", "50"])


class TestModeScoping:
    """--sample-* require --batch (or implicit auto-batch with 2+ RSIDs)."""

    def test_sample_in_single_mode_errors(self, capsys: pytest.CaptureFixture[str], tmp_path: object) -> None:
        from aa_auto_sdr.__main__ import main

        with pytest.raises(SystemExit) as exc:
            main(["rs1", "--sample", "3"])
        assert exc.value.code == ExitCode.USAGE.value
        captured = capsys.readouterr()
        assert "--sample requires --batch" in captured.err + captured.out

    def test_sample_seed_without_sample_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        from aa_auto_sdr.__main__ import main

        with pytest.raises(SystemExit) as exc:
            main(["--batch", "rs1", "rs2", "--sample-seed", "42"])
        assert exc.value.code == ExitCode.USAGE.value
        captured = capsys.readouterr()
        assert "--sample-seed requires --sample" in captured.err + captured.out

    def test_sample_stratified_without_sample_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        from aa_auto_sdr.__main__ import main

        with pytest.raises(SystemExit) as exc:
            main(["--batch", "rs1", "rs2", "--sample-stratified"])
        assert exc.value.code == ExitCode.USAGE.value
        captured = capsys.readouterr()
        assert "--sample-stratified requires --sample" in captured.err + captured.out

    def test_sample_zero_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        from aa_auto_sdr.__main__ import main

        with pytest.raises(SystemExit) as exc:
            main(["--batch", "rs1", "rs2", "--sample", "0"])
        assert exc.value.code == ExitCode.USAGE.value
        captured = capsys.readouterr()
        assert "--sample must be >= 1" in captured.err + captured.out

    def test_sample_negative_errors(self, capsys: pytest.CaptureFixture[str]) -> None:
        from aa_auto_sdr.__main__ import main

        with pytest.raises(SystemExit) as exc:
            main(["--batch", "rs1", "rs2", "--sample", "-3"])
        assert exc.value.code == ExitCode.USAGE.value
