"""CLI argparse + dispatch wiring for v1.11.0 inventory flags."""

from __future__ import annotations

import pytest

from aa_auto_sdr.cli.parser import build_parser


class TestInventoryArgparse:
    def test_inventory_summary_flag_default_false(self) -> None:
        ns = build_parser().parse_args(["rs1"])
        assert ns.inventory_summary is False

    def test_inventory_summary_flag_set(self) -> None:
        ns = build_parser().parse_args(["rs1", "--inventory-summary"])
        assert ns.inventory_summary is True

    def test_inventory_summary_no_positional(self) -> None:
        ns = build_parser().parse_args(["--inventory-summary"])
        assert ns.inventory_summary is True
        assert ns.rsids == []


class TestInventorySummaryStatsMutex:
    def test_inventory_summary_with_stats_rejected(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["rs1", "--inventory-summary", "--stats"])


class TestInventoryOnlyRejected:
    def test_inventory_only_rejected(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(["rs1", "--inventory-only"])


class TestInventoryDispatch:
    def test_inventory_summary_dispatches_to_inventory_run(self, capsys: pytest.CaptureFixture[str]) -> None:
        """End-to-end: `aa_auto_sdr rs1 rs2 --inventory-summary --format json`
        reaches inventory.run."""
        from unittest.mock import patch

        from aa_auto_sdr.__main__ import main
        from aa_auto_sdr.cli.commands import inventory as inv_command

        called_with: dict = {}

        def _capture_run(**kwargs: object) -> int:
            called_with.update(kwargs)
            return 0

        with patch.object(inv_command, "run", side_effect=_capture_run) as mock_run:
            main(["rs1", "rs2", "--inventory-summary", "--format", "json"])

        assert mock_run.called
        assert called_with["rsids"] == ["rs1", "rs2"]
        assert called_with["format_name"] == "json"
