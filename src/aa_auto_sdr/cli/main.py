"""CLI dispatcher — routes parsed args to a command handler."""

from __future__ import annotations

import sys

from aa_auto_sdr.cli.commands import config as config_cmd
from aa_auto_sdr.cli.commands import generate as generate_cmd
from aa_auto_sdr.cli.parser import build_parser

_EXIT_USAGE = 2


def run(argv: list[str]) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)

    if ns.profile_add:
        return config_cmd.profile_add(ns.profile_add)

    if ns.show_config:
        return config_cmd.show_config(profile=ns.profile)

    if not ns.rsid:
        parser.print_usage(file=sys.stderr)
        return _EXIT_USAGE

    return generate_cmd.run(
        rsid=ns.rsid,
        output_dir=ns.output_dir,
        format_name=ns.format,
        profile=ns.profile,
    )
