"""CLI dispatcher — routes parsed args to a command handler."""

from __future__ import annotations

import sys

from aa_auto_sdr.cli.commands import config as config_cmd
from aa_auto_sdr.cli.commands import generate as generate_cmd
from aa_auto_sdr.cli.parser import build_parser

_EXIT_USAGE = 2
_EXIT_NOT_IMPLEMENTED = 1


def run(argv: list[str]) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)

    # Profile/config actions
    if ns.profile_add:
        return config_cmd.profile_add(ns.profile_add)
    if ns.show_config:
        return config_cmd.show_config(profile=ns.profile)

    # Discovery + inspect actions (handlers added in later tasks; stub for now)
    if ns.list_reportsuites:
        return _stub_action("--list-reportsuites")
    if ns.list_virtual_reportsuites:
        return _stub_action("--list-virtual-reportsuites")
    if ns.describe_reportsuite:
        return _stub_action("--describe-reportsuite")
    if ns.list_metrics:
        return _stub_action("--list-metrics")
    if ns.list_dimensions:
        return _stub_action("--list-dimensions")
    if ns.list_segments:
        return _stub_action("--list-segments")
    if ns.list_calculated_metrics:
        return _stub_action("--list-calculated-metrics")
    if ns.list_classification_datasets:
        return _stub_action("--list-classification-datasets")

    # Generate (positional RSID) — default --format to "excel" if omitted
    if not ns.rsid:
        parser.print_usage(sys.stderr)
        return _EXIT_USAGE

    return generate_cmd.run(
        rsid=ns.rsid,
        output_dir=ns.output_dir,
        format_name=ns.format or "excel",
        profile=ns.profile,
    )


def _stub_action(name: str) -> int:
    print(f"error: {name} not yet implemented in this build", flush=True)
    return _EXIT_NOT_IMPLEMENTED
