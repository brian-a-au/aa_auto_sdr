"""CLI dispatcher — routes parsed args to a command handler."""

from __future__ import annotations

import sys
from pathlib import Path

from aa_auto_sdr.cli.commands import config as config_cmd
from aa_auto_sdr.cli.commands import generate as generate_cmd
from aa_auto_sdr.cli.parser import build_parser
from aa_auto_sdr.core.exit_codes import ExitCode


def run(argv: list[str]) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)

    # Profile/config actions
    if ns.profile_add:
        return config_cmd.profile_add(ns.profile_add)
    if ns.show_config:
        return config_cmd.show_config(profile=ns.profile)

    # v1.1 — snapshot lifecycle
    if ns.list_snapshots:
        from aa_auto_sdr.cli.commands import snapshots as snap_cmd

        return snap_cmd.list_run(
            profile=ns.profile,
            rsid=ns.rsid,
            format_name=ns.format,
        )
    if ns.prune_snapshots:
        from aa_auto_sdr.cli.commands import snapshots as snap_cmd

        return snap_cmd.prune_run(
            profile=ns.profile,
            rsid=ns.rsid,
            keep_last=ns.keep_last,
            keep_since=ns.keep_since,
            dry_run=ns.dry_run,
        )

    # v1.1 — profile commands
    if ns.profile_list:
        from aa_auto_sdr.cli.commands import profiles as prof_cmd

        return prof_cmd.list_run(format_name=ns.format)
    if ns.profile_test:
        from aa_auto_sdr.cli.commands import profiles as prof_cmd

        return prof_cmd.test_run(ns.profile_test)
    if ns.profile_show:
        from aa_auto_sdr.cli.commands import profiles as prof_cmd

        return prof_cmd.show_run(ns.profile_show)
    if ns.profile_import:
        from aa_auto_sdr.cli.commands import profiles as prof_cmd

        name, src_path = ns.profile_import
        return prof_cmd.import_run(name, src_path)

    # Fast-path actions (also reachable via slow path if positional ordering forced argparse)
    if ns.exit_codes:
        from aa_auto_sdr.cli.commands.exit_codes import run_list_exit_codes

        return run_list_exit_codes()
    if ns.explain_exit_code is not None:
        from aa_auto_sdr.cli.commands.exit_codes import run_explain_exit_code

        return run_explain_exit_code(ns.explain_exit_code)
    if ns.completion:
        from aa_auto_sdr.cli.commands.completion import run_completion

        return run_completion(ns.completion)

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

    # Diff (v0.7) — snapshot comparison
    if ns.diff:
        if ns.rsid:
            print("error: --diff cannot be combined with a positional RSID", flush=True)
            return ExitCode.USAGE.value
        from aa_auto_sdr.cli.commands import diff as diff_cmd

        ignore = frozenset(f.strip() for f in (ns.ignore_fields or "").split(",") if f.strip())
        return diff_cmd.run(
            a=ns.diff[0],
            b=ns.diff[1],
            format_name=ns.format,
            output=ns.output,
            profile=ns.profile,
            side_by_side=ns.side_by_side,
            summary=ns.summary,
            ignore_fields=ignore,
        )

    # Batch (v0.5) — sequential multi-RSID generation
    if ns.batch:
        if ns.output == "-":
            print(
                "error: --output - is ambiguous for --batch "
                "(multiple SDRs cannot share a single stream); use --output-dir instead",
                flush=True,
            )
            return ExitCode.OUTPUT.value
        from aa_auto_sdr.cli.commands import batch as batch_cmd

        return batch_cmd.run(
            rsids=ns.batch,
            output_dir=ns.output_dir,
            format_name=ns.format or "excel",
            profile=ns.profile,
            snapshot=ns.snapshot,
            auto_snapshot=ns.auto_snapshot,
            auto_prune=ns.auto_prune,
            keep_last=ns.keep_last,
            keep_since=ns.keep_since,
        )

    # Generate (positional RSID) — default --format to "excel" if omitted
    if not ns.rsid:
        parser.print_usage(sys.stderr)
        return ExitCode.USAGE.value

    output_dir: Path = Path("-") if ns.output == "-" else ns.output_dir
    return generate_cmd.run(
        rsid=ns.rsid,
        output_dir=output_dir,
        format_name=ns.format or "excel",
        profile=ns.profile,
        snapshot=ns.snapshot,
        auto_snapshot=ns.auto_snapshot,
        auto_prune=ns.auto_prune,
        keep_last=ns.keep_last,
        keep_since=ns.keep_since,
    )


def _stub_action(name: str) -> int:
    print(f"error: {name} not yet implemented in this build", flush=True)
    return ExitCode.GENERIC.value
