"""CLI dispatcher — routes parsed args to a command handler."""

from __future__ import annotations

import sys
from pathlib import Path

from aa_auto_sdr.cli.commands import config as config_cmd
from aa_auto_sdr.cli.commands import generate as generate_cmd
from aa_auto_sdr.cli.parser import build_parser

_EXIT_USAGE = 2
_EXIT_NOT_IMPLEMENTED = 1
_EXIT_OUTPUT = 15


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
        from aa_auto_sdr.cli.commands import discovery as discovery_cmd

        return discovery_cmd.run_list_reportsuites(
            profile=ns.profile,
            format_name=ns.format,
            output=ns.output,
            name_filter=ns.filter,
            name_exclude=ns.exclude,
            sort_field=ns.sort,
            limit=ns.limit,
        )
    if ns.list_virtual_reportsuites:
        from aa_auto_sdr.cli.commands import discovery as discovery_cmd

        return discovery_cmd.run_list_virtual_reportsuites(
            profile=ns.profile,
            format_name=ns.format,
            output=ns.output,
            name_filter=ns.filter,
            name_exclude=ns.exclude,
            sort_field=ns.sort,
            limit=ns.limit,
        )
    if ns.describe_reportsuite:
        from aa_auto_sdr.cli.commands import inspect as inspect_cmd

        return inspect_cmd.run_describe_reportsuite(
            identifier=ns.describe_reportsuite,
            profile=ns.profile,
            format_name=ns.format,
            output=ns.output,
        )

    list_inspect_actions = (
        ("list_metrics", "run_list_metrics"),
        ("list_dimensions", "run_list_dimensions"),
        ("list_segments", "run_list_segments"),
        ("list_calculated_metrics", "run_list_calculated_metrics"),
        ("list_classification_datasets", "run_list_classification_datasets"),
    )
    for attr, fn_name in list_inspect_actions:
        identifier = getattr(ns, attr)
        if identifier:
            from aa_auto_sdr.cli.commands import inspect as inspect_cmd

            handler = getattr(inspect_cmd, fn_name)
            return handler(
                identifier=identifier,
                profile=ns.profile,
                format_name=ns.format,
                output=ns.output,
                name_filter=ns.filter,
                name_exclude=ns.exclude,
                sort_field=ns.sort,
                limit=ns.limit,
            )

    # Batch (v0.5) — sequential multi-RSID generation
    if ns.batch:
        if ns.output == "-":
            print(
                "error: --output - is ambiguous for --batch "
                "(multiple SDRs cannot share a single stream); use --output-dir instead",
                flush=True,
            )
            return _EXIT_OUTPUT
        from aa_auto_sdr.cli.commands import batch as batch_cmd

        return batch_cmd.run(
            rsids=ns.batch,
            output_dir=ns.output_dir,
            format_name=ns.format or "excel",
            profile=ns.profile,
            snapshot=ns.snapshot,
        )

    # Generate (positional RSID) — default --format to "excel" if omitted
    if not ns.rsid:
        parser.print_usage(sys.stderr)
        return _EXIT_USAGE

    output_dir: Path = Path("-") if ns.output == "-" else ns.output_dir
    return generate_cmd.run(
        rsid=ns.rsid,
        output_dir=output_dir,
        format_name=ns.format or "excel",
        profile=ns.profile,
        snapshot=ns.snapshot,
    )


def _stub_action(name: str) -> int:
    print(f"error: {name} not yet implemented in this build", flush=True)
    return _EXIT_NOT_IMPLEMENTED
