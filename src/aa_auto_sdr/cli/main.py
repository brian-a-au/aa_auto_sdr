"""CLI dispatcher — routes parsed args to a command handler."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from aa_auto_sdr.cli.commands import config as config_cmd
from aa_auto_sdr.cli.commands import generate as generate_cmd
from aa_auto_sdr.cli.parser import build_parser
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.core.logging import infer_run_mode, setup_logging

logger = logging.getLogger(__name__)


def _argv_summary(argv: list[str]) -> list[str]:
    """Return only the flag names from argv (anything starting with '-').

    Used as ``extra={"argv_summary": ...}`` on run_start. Positional values
    (RSIDs, file paths) are never included — they ride on their own
    structured fields. See LOGGING_STYLE.md §message-style rules."""
    return [a for a in argv if a.startswith("-")]


def run(argv: list[str]) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    setup_logging(ns)
    # If setup_logging coerced an invalid --log-level back to INFO, mirror
    # that decision into the file handler now that it is attached. Spec §7.2
    # row 4 — soft warning, no extras required.
    requested_level = (getattr(ns, "log_level", None) or "INFO").upper()
    if requested_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        logger.warning("invalid log_level=%s coerced to INFO", requested_level)
    run_mode = infer_run_mode(ns)
    logger.info(
        "run_start mode=%s",
        run_mode,
        extra={"run_mode": run_mode, "argv_summary": _argv_summary(argv)},
    )
    started = time.monotonic()
    try:
        exit_code = _dispatch(ns, parser)
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.error(
            "run_failure error_class=%s",
            type(exc).__name__,
            extra={
                "exit_code": ExitCode.GENERIC.value,
                "error_class": type(exc).__name__,
                "duration_ms": duration_ms,
            },
        )
        raise
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "run_complete exit_code=%s duration_ms=%s",
        exit_code,
        duration_ms,
        extra={"exit_code": exit_code, "duration_ms": duration_ms},
    )
    return exit_code


def _dispatch(ns: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """All command dispatch that previously lived directly in run().

    Extracted so run() can wrap it in a single try/except for run_failure
    instrumentation without proliferating log calls before every existing
    ``return X.value`` in the dispatch chain. Verbatim move — no behavior
    changes inside this helper. ``parser`` is threaded through so the
    no-args USAGE branch can still call ``parser.print_usage(sys.stderr)``."""
    from aa_auto_sdr.core import colors

    colors.set_theme(getattr(ns, "color_theme", "default"))
    rsids: list[str] = list(ns.rsids)

    # Reject positional RSIDs combined with actions that take their identifier
    # inline. Without this guard, `aa_auto_sdr --list-metrics RS1 RS2` would
    # silently drop RS2 (the user likely meant "list metrics for both" — fail
    # loud rather than ignore). The diff and snapshot-lifecycle actions have
    # their own action-specific positional limits below.
    _inline_id_actions = (
        ("describe_reportsuite", "--describe-reportsuite"),
        ("list_metrics", "--list-metrics"),
        ("list_dimensions", "--list-dimensions"),
        ("list_segments", "--list-segments"),
        ("list_calculated_metrics", "--list-calculated-metrics"),
        ("list_classification_datasets", "--list-classification-datasets"),
        ("profile_add", "--profile-add"),
        ("profile_test", "--profile-test"),
        ("profile_show", "--profile-show"),
    )
    for attr, flag in _inline_id_actions:
        if getattr(ns, attr) and rsids:
            print(
                f"error: {flag} takes its RSID inline; extra positional arguments are not supported",
                flush=True,
            )
            return ExitCode.USAGE.value
    if ns.profile_import and rsids:
        print(
            "error: --profile-import takes <NAME> <FILE> inline; extra positional arguments are not supported",
            flush=True,
        )
        return ExitCode.USAGE.value

    # Profile/config actions
    if ns.profile_add:
        return config_cmd.profile_add(ns.profile_add)
    if ns.show_config:
        return config_cmd.show_config(profile=ns.profile)

    # v1.2 — config introspection actions (no auth required)
    if ns.config_status:
        return config_cmd.config_status(profile=ns.profile)
    if ns.validate_config:
        return config_cmd.validate_config(profile=ns.profile)
    if ns.sample_config:
        return config_cmd.sample_config()

    # v1.2 — stats action
    if ns.stats:
        from aa_auto_sdr.cli.commands import stats as stats_cmd

        return stats_cmd.run(rsids=rsids, profile=ns.profile, format_name=ns.format)

    # v1.2 — interactive action
    if ns.interactive:
        from aa_auto_sdr.cli.commands import interactive as interactive_cmd

        return interactive_cmd.run(profile=ns.profile)

    # v1.1 — snapshot lifecycle. Optional positional <RSID> narrows to one suite;
    # multiple positionals are a usage error (the filter is single-valued).
    if ns.list_snapshots:
        if len(rsids) > 1:
            print(
                "error: --list-snapshots accepts at most one positional <RSID> filter",
                flush=True,
            )
            return ExitCode.USAGE.value
        from aa_auto_sdr.cli.commands import snapshots as snap_cmd

        return snap_cmd.list_run(
            profile=ns.profile,
            rsid=rsids[0] if rsids else None,
            format_name=ns.format,
        )
    if ns.prune_snapshots:
        if len(rsids) > 1:
            print(
                "error: --prune-snapshots accepts at most one positional <RSID> filter",
                flush=True,
            )
            return ExitCode.USAGE.value
        from aa_auto_sdr.cli.commands import snapshots as snap_cmd

        return snap_cmd.prune_run(
            profile=ns.profile,
            rsid=rsids[0] if rsids else None,
            keep_last=ns.keep_last,
            keep_since=ns.keep_since,
            dry_run=ns.dry_run,
            assume_yes=ns.yes,
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
        return prof_cmd.import_run(name, src_path, overwrite=ns.profile_overwrite)

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
        if rsids:
            print("error: --diff cannot be combined with positional RSIDs", flush=True)
            return ExitCode.USAGE.value
        from aa_auto_sdr.cli.commands import diff as diff_cmd

        ignore = frozenset(f.strip() for f in (ns.ignore_fields or "").split(",") if f.strip())
        labels: tuple[str, str] | None = None
        if ns.diff_labels:
            # `--diff-labels A=baseline B=candidate` → ("baseline", "candidate")
            a_label = ns.diff_labels[0].split("=", 1)[-1]
            b_label = ns.diff_labels[1].split("=", 1)[-1]
            labels = (a_label, b_label)
        show_only = frozenset(t.strip() for t in (ns.show_only or "").split(",") if t.strip())
        return diff_cmd.run(
            a=ns.diff[0],
            b=ns.diff[1],
            format_name=ns.format,
            output=ns.output,
            profile=ns.profile,
            side_by_side=ns.side_by_side,
            summary=ns.summary,
            ignore_fields=ignore,
            quiet=ns.quiet_diff,
            labels=labels,
            reverse=ns.reverse_diff,
            changes_only=ns.changes_only,
            show_only=show_only,
            max_issues=ns.max_issues,
            warn_threshold=ns.warn_threshold,
            color_theme=ns.color_theme,
        )

    # v1.2.1 — both want stdout: reject before any work happens.
    if ns.run_summary_json == "-" and ns.output == "-":
        print(
            "error: --run-summary-json - and --output - both want stdout (use a path for one)",
            flush=True,
        )
        return ExitCode.OUTPUT.value

    # Combine explicit --batch flag with positional RSIDs into a single list.
    # `--batch RS1 RS2` is the original v0.5 form; `aa_auto_sdr RS1 RS2` (v1.1+) is
    # the auto-inferred shorthand. Mixing them is rejected for clarity.
    explicit_batch = bool(ns.batch)
    if explicit_batch and rsids:
        print(
            "error: cannot combine --batch with positional RSIDs (use one form or the other)",
            flush=True,
        )
        return ExitCode.USAGE.value
    if explicit_batch:
        rsids = list(ns.batch)

    # No identifiers at all and no other action matched → usage error.
    if not rsids:
        parser.print_usage(sys.stderr)
        return ExitCode.USAGE.value

    # Route to batch if EITHER --batch was explicit OR multiple positionals were
    # given. Single positional with no --batch goes through the single-generate
    # path. (Note: `--batch RS1` with one RSID still uses batch — the flag opts in
    # to the batch summary banner / partial-success exit code even for one RSID.)
    if explicit_batch or len(rsids) > 1:
        if ns.output == "-":
            print(
                "error: --output - is ambiguous for batch runs "
                "(multiple SDRs cannot share a single stream); use --output-dir instead",
                flush=True,
            )
            return ExitCode.OUTPUT.value
        from aa_auto_sdr.cli.commands import batch as batch_cmd

        return batch_cmd.run(
            rsids=rsids,
            output_dir=ns.output_dir,
            format_name=ns.format or "excel",
            profile=ns.profile,
            snapshot=ns.snapshot,
            auto_snapshot=ns.auto_snapshot,
            auto_prune=ns.auto_prune,
            keep_last=ns.keep_last,
            keep_since=ns.keep_since,
            dry_run=ns.dry_run,
            metrics_only=ns.metrics_only,
            dimensions_only=ns.dimensions_only,
            open_after=ns.open,
            assume_yes=ns.yes,
            show_timings=ns.show_timings,
            run_summary_json=ns.run_summary_json,
        )

    # Single identifier → generate. Default --format to "excel" if omitted.
    output_dir: Path = Path("-") if ns.output == "-" else ns.output_dir
    return generate_cmd.run(
        rsid=rsids[0],
        output_dir=output_dir,
        format_name=ns.format or "excel",
        profile=ns.profile,
        snapshot=ns.snapshot,
        auto_snapshot=ns.auto_snapshot,
        auto_prune=ns.auto_prune,
        keep_last=ns.keep_last,
        keep_since=ns.keep_since,
        dry_run=ns.dry_run,
        metrics_only=ns.metrics_only,
        dimensions_only=ns.dimensions_only,
        open_after=ns.open,
        assume_yes=ns.yes,
        show_timings=ns.show_timings,
        run_summary_json=ns.run_summary_json,
    )


def _stub_action(name: str) -> int:
    print(f"error: {name} not yet implemented in this build", flush=True)
    return ExitCode.GENERIC.value
