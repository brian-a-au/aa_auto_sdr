"""CLI dispatcher — routes parsed args to a command handler."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.cli.agent_output import (
    DIFF_STDOUT_FORMATS,
    DISCOVERY_STDOUT_FORMATS,
    is_stdout_path,
    resolve_agent_output_path,
)
from aa_auto_sdr.cli.commands import config as config_cmd
from aa_auto_sdr.cli.commands import generate as generate_cmd
from aa_auto_sdr.cli.commands._shared import resolve_snapshot_dir
from aa_auto_sdr.cli.parser import (
    _apply_agent_mode_defaults,
    _configured_long_options,
    build_parser,
)
from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.core.logging import infer_run_mode, setup_logging

logger = logging.getLogger(__name__)


def _argv_summary(argv: list[str]) -> list[str]:
    """Return only the flag names from argv (anything starting with '-').

    Used as ``extra={"argv_summary": ...}`` on run_start. Positional values
    (RSIDs, file paths) are never included — they ride on their own
    structured fields. See LOGGING_STYLE.md §message-style rules."""
    return [a for a in argv if a.startswith("-")]


def _derive_quiet_from_output_destination(ns: argparse.Namespace) -> None:
    """Honor the documented contract that stdout-bound output implies --quiet.

    Mutates ``ns.quiet`` in place. Without this, INFO records on stderr leak
    into streams agents / scripts are reading on stdout. Applies to both
    ``--output -`` and ``--run-summary-json -``. Idempotent when ``--quiet``
    was already explicit. Must run AFTER ``_apply_agent_mode_defaults`` so
    the preset's implicit ``--output -`` is visible, and BEFORE
    ``setup_logging`` so the console handler is wired at the right level.
    """
    if getattr(ns, "quiet", False):
        return
    if is_stdout_path(getattr(ns, "output", None)) or is_stdout_path(getattr(ns, "run_summary_json", None)):
        ns.quiet = True


def _resolve_retry_policy(ns: argparse.Namespace) -> RetryPolicy:
    """Build a RetryPolicy from the parsed CLI namespace.

    Lives in cli/ (not api/resilience.py) so the resilience module stays
    ignorant of CLI vocabulary — argparse dest names (`retry_base_delay`,
    `retry_max_delay`) are a CLI concern, not a policy-domain concern.
    Defaults are filled from RetryPolicy()'s own defaults; the constructor's
    __post_init__ raises ValueError on cross-flag invariant violations
    (e.g., max_delay < base_delay), which run() catches and translates to
    USAGE (2) before any expensive work.
    """
    defaults = RetryPolicy()
    return RetryPolicy(
        max_retries=ns.max_retries if ns.max_retries is not None else defaults.max_retries,
        base_delay=ns.retry_base_delay if ns.retry_base_delay is not None else defaults.base_delay,
        max_delay=ns.retry_max_delay if ns.retry_max_delay is not None else defaults.max_delay,
    )


def _apply_quality_auto_enable(ns: argparse.Namespace) -> None:
    """Auto-enable v1.9.0 audits when v1.12.0 quality flags are set without them.

    Per spec §3.9: `--quality-report` or `--fail-on-quality` need at least one
    audit to produce findings. If neither audit flag is on, enable both and
    emit `quality_auto_enabled` (spec §3.12) so users see the implicit toggle
    in the log stream.
    """
    if (getattr(ns, "quality_report", None) or getattr(ns, "fail_on_quality", None)) and not (
        getattr(ns, "audit_naming", False) or getattr(ns, "flag_stale", False)
    ):
        ns.audit_naming = True
        ns.flag_stale = True
        logger.info(
            "quality_auto_enabled audit_naming=true flag_stale=true",
            extra={"audit_naming": True, "flag_stale": True},
        )


def _validate_watch_modifiers(ns: argparse.Namespace) -> int:
    """Reject --interval / non-default --watch-threshold without --watch.

    Returns ExitCode.OK if the namespace is consistent, ExitCode.USAGE
    (printing a message to stderr) if a modifier was set without --watch.

    Lives in cli/main.py rather than cli/commands/watch.py because the watch
    handler only runs when --watch is true; the bare --interval / bare
    --watch-threshold cases never reach it otherwise.
    """
    if getattr(ns, "watch", False):
        return int(ExitCode.OK)
    if getattr(ns, "interval", None) is not None:
        print("error: --interval requires --watch", file=sys.stderr)
        return int(ExitCode.USAGE)
    if getattr(ns, "watch_threshold", 1) != 1:
        print("error: --watch-threshold requires --watch", file=sys.stderr)
        return int(ExitCode.USAGE)
    return int(ExitCode.OK)


def _validate_git_modifiers(ns: argparse.Namespace) -> int:
    """Reject --git-push / --git-message without --git-commit, and --git-commit
    with non-generating actions.

    Returns ExitCode.OK if consistent, ExitCode.USAGE (with stderr message)
    otherwise.
    """
    git_commit = getattr(ns, "git_commit", False)
    git_push = getattr(ns, "git_push", False)
    git_message = getattr(ns, "git_message", None)

    if git_push and not git_commit:
        print("error: --git-push requires --git-commit", file=sys.stderr)
        return int(ExitCode.USAGE)
    if git_message is not None and not git_commit:
        print("error: --git-message requires --git-commit", file=sys.stderr)
        return int(ExitCode.USAGE)

    if not git_commit:
        return int(ExitCode.OK)

    non_generating_action_set = (
        getattr(ns, "diff", None) is not None
        or bool(getattr(ns, "stats", False))
        or bool(getattr(ns, "list_reportsuites", False))
        or bool(getattr(ns, "list_virtual_reportsuites", False))
        or bool(getattr(ns, "describe_reportsuite", False))
        or getattr(ns, "list_metrics", None) is not None
        or getattr(ns, "list_dimensions", None) is not None
        or getattr(ns, "list_segments", None) is not None
        or getattr(ns, "list_calculated_metrics", None) is not None
        or getattr(ns, "list_classification_datasets", None) is not None
        or getattr(ns, "trending_window", None) is not None
        or bool(getattr(ns, "compare_with_prev", False))
        or bool(getattr(ns, "inventory_summary", False))
    )
    if non_generating_action_set:
        print(
            "error: --git-commit requires an SDR-generating action (bare RSID, --batch, or --watch)",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)
    return int(ExitCode.OK)


def _validate_template_modifiers(ns: argparse.Namespace) -> int:
    """Reject template flags that don't compose. Returns ExitCode.OK or USAGE.

    Per spec §3.9. Lives here (not in cli/commands/generate.py) for the same
    reason _validate_watch_modifiers does: validation must run before dispatch
    so non-generating actions also reject --template cleanly.
    """
    template = getattr(ns, "template", None)
    organization = getattr(ns, "template_organization", None)

    if organization is not None and template is None:
        print("error: --template-organization requires --template", file=sys.stderr)
        return int(ExitCode.USAGE)

    if template is None:
        return int(ExitCode.OK)

    if not template.exists():
        print(f"error: Template not found: {template}", file=sys.stderr)
        return int(ExitCode.USAGE)
    if not template.is_file():
        print(f"error: Template path is not a file: {template}", file=sys.stderr)
        return int(ExitCode.USAGE)
    if template.suffix.lower() != ".xlsx":
        print(f"error: Template must be a .xlsx file: {template}", file=sys.stderr)
        return int(ExitCode.USAGE)

    non_generating = (
        getattr(ns, "diff", None) is not None
        or bool(getattr(ns, "stats", False))
        or bool(getattr(ns, "list_reportsuites", False))
        or bool(getattr(ns, "list_virtual_reportsuites", False))
        or bool(getattr(ns, "describe_reportsuite", False))
        or getattr(ns, "list_metrics", None) is not None
        or getattr(ns, "list_dimensions", None) is not None
        or getattr(ns, "list_segments", None) is not None
        or getattr(ns, "list_calculated_metrics", None) is not None
        or getattr(ns, "list_classification_datasets", None) is not None
        or getattr(ns, "trending_window", None) is not None
        or bool(getattr(ns, "compare_with_prev", False))
        or bool(getattr(ns, "inventory_summary", False))
        or bool(getattr(ns, "watch", False))
    )
    if non_generating:
        print(
            "error: --template requires an SDR-generating action (single or --batch)",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)

    # Resolve the user's --format to the concrete format set and ensure it
    # contains 'excel'. We use the registry's alias map for this; if --format
    # is unset, the default is 'excel' so the check passes naturally.
    from aa_auto_sdr.output import registry as _registry

    try:
        resolved = _registry.resolve_formats(getattr(ns, "format", None) or "excel")
    except KeyError:
        # Unknown format — generate path will surface its own error. Don't
        # double-report here.
        return int(ExitCode.OK)
    if "excel" not in resolved and "excel-template" not in resolved:
        print(
            "error: --template requires --format excel (or an alias that includes excel)",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)
    return int(ExitCode.OK)


# Actions that conflict with --push-to-notion: presence of any one means the
# user asked for a different mode alongside push, which would silently win or
# silently lose. Reject loudly. The tuple lists (attr, expected-truthy-check,
# flag-name) so the message can name the offending flag.
_PUSH_TO_NOTION_CONFLICTS: tuple[tuple[str, str], ...] = (
    ("diff", "--diff"),
    ("batch", "--batch"),
    ("watch", "--watch"),
    ("list_reportsuites", "--list-reportsuites"),
    ("list_virtual_reportsuites", "--list-virtual-reportsuites"),
    ("describe_reportsuite", "--describe-reportsuite"),
    ("list_metrics", "--list-metrics"),
    ("list_dimensions", "--list-dimensions"),
    ("list_segments", "--list-segments"),
    ("list_calculated_metrics", "--list-calculated-metrics"),
    ("list_classification_datasets", "--list-classification-datasets"),
    ("list_snapshots", "--list-snapshots"),
    ("prune_snapshots", "--prune-snapshots"),
    ("trending_window", "--trending-window"),
    ("compare_with_prev", "--compare-with-prev"),
    ("inventory_summary", "--inventory-summary"),
    ("stats", "--stats"),
    ("interactive", "--interactive"),
    # Config / profile top-level modes also dispatched in _dispatch — without
    # this guard, push would silently win and the user's config inspection
    # request would be dropped. (--version and --help are intercepted by
    # argparse before _dispatch runs, so they never reach this validator.)
    ("show_config", "--show-config"),
    ("config_status", "--config-status"),
    ("validate_config", "--validate-config"),
    ("sample_config", "--sample-config"),
    ("profile_list", "--profile-list"),
    ("profile_add", "--profile-add"),
    ("profile_test", "--profile-test"),
    ("profile_show", "--profile-show"),
    ("profile_import", "--profile-import"),
    # Fast-path action flags only short-circuit in __main__.py when they are
    # argv[0]; if a user puts them after --push-to-notion (e.g.
    # ``--push-to-notion sdr.json --exit-codes``) dispatch reaches this
    # validator and push would silently win. Reject loudly here too.
    ("exit_codes", "--exit-codes"),
    ("explain_exit_code", "--explain-exit-code"),
    ("completion", "--completion"),
)


def _reject_push_to_notion_conflicts(ns: argparse.Namespace) -> int:
    """Reject co-presence of --push-to-notion with another top-level mode.

    Without this guard, dispatch order would silently pick push and discard
    the user's other requested action (e.g. ``--push-to-notion file --diff a b``
    would push and ignore the diff). v1.18.0.
    """
    for attr, flag in _PUSH_TO_NOTION_CONFLICTS:
        val = getattr(ns, attr, None)
        # `--explain-exit-code 0` is a legitimate user request (ExitCode.OK is
        # in EXPLANATIONS) but int(0) is falsy — fall back to an explicit
        # None check for that attr so the literal 0 still trips the guard.
        triggered = (val is not None) if attr == "explain_exit_code" else bool(val)
        if triggered:
            print(
                f"error: --push-to-notion cannot be combined with {flag}",
                file=sys.stderr,
            )
            return int(ExitCode.USAGE)
    if getattr(ns, "rsids", None):
        print(
            "error: --push-to-notion does not accept positional RSIDs (it republishes the given JSON file)",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)
    return int(ExitCode.OK)


def _reject_standalone_mode_conflicts(ns: argparse.Namespace, mode_flag: str, *, sibling: bool) -> int:
    """Reject co-presence of a standalone Notion mode with any other top-level mode.

    The standalone Notion modes (``--notion-prune-orphans``,
    ``--notion-repair-database``, ``--notion-create-database``) own the whole
    run: combining one with any other top-level action would let dispatch order
    silently pick one and drop the other. Reuse the canonical
    :data:`_PUSH_TO_NOTION_CONFLICTS` enumeration (every non-generating
    top-level action — discovery/inspection, snapshot lifecycle, config/profile,
    fast-path) so newly-added modes are covered automatically, then reject
    generation (positional RSIDs), ``--push-to-notion``, and any sibling
    standalone mode the caller flags via ``sibling``.

    Returns ``ExitCode.USAGE`` (after printing to stderr) on conflict, else
    ``ExitCode.OK``. The mutual-exclusion of the standalone modes against each
    other is the caller's responsibility where a more specific message applies
    (e.g. prune + repair).
    """
    for attr, flag in _PUSH_TO_NOTION_CONFLICTS:
        val = getattr(ns, attr, None)
        triggered = (val is not None) if attr == "explain_exit_code" else bool(val)
        if triggered:
            print(f"error: {mode_flag} cannot be combined with {flag}", file=sys.stderr)
            return int(ExitCode.USAGE)
    if bool(getattr(ns, "rsids", []) or []) or bool(getattr(ns, "push_to_notion", None)) or sibling:
        print(f"error: {mode_flag} cannot be combined with generation or other modes", file=sys.stderr)
        return int(ExitCode.USAGE)
    return int(ExitCode.OK)


def _validate_notion_modifiers(ns: argparse.Namespace) -> int:
    """Reject mutually-incompatible Notion flag combinations.

    Returns ExitCode.OK if consistent, ExitCode.USAGE (with stderr
    message) otherwise.

    v1.19.0 rules:
      - --notion-registry-database X --no-notion-registry  (operator confusion)
      - --notion-registry-database X without a notion mode or repair (flag meaningless)
      - --no-notion-registry without a notion mode         (flag meaningless)
      Note: --notion-repair-database is exempt from the registry-database check because
      it legitimately uses --notion-registry-database as its database-id source.

    v1.20.0 rules:
      - --notion-prune-orphans / --notion-repair-database are standalone modes
      - --notion-company requires a notion mode
      - --yes (for notion) requires --notion-prune-orphans or --notion-repair-database
    """
    in_notion_mode = getattr(ns, "format", None) == "notion" or bool(getattr(ns, "push_to_notion", None))
    repair = bool(getattr(ns, "notion_repair_database", False))
    create = bool(getattr(ns, "notion_create_database", False))

    # v1.21.0 — --notion-database-title is meaningless without --notion-create-database.
    if getattr(ns, "notion_database_title", None) is not None and not create:
        print(
            "error: --notion-database-title requires --notion-create-database",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)

    # v1.19.0 — mutual rejection of the two registry flags.
    if getattr(ns, "notion_registry_database", None) and getattr(ns, "no_notion_registry", False):
        print(
            "error: --notion-registry-database and --no-notion-registry cannot be combined",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)

    # v1.19.0 — registry flags require a notion mode.
    # Exempt repair: --notion-repair-database legitimately uses --notion-registry-database
    # as its database-id source without entering in_notion_mode.
    if getattr(ns, "notion_registry_database", None) and not in_notion_mode and not repair:
        print(
            "error: --notion-registry-database requires --format notion or --push-to-notion",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)
    if getattr(ns, "no_notion_registry", False) and not in_notion_mode:
        print(
            "error: --no-notion-registry requires --format notion or --push-to-notion",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)

    prune = bool(getattr(ns, "notion_prune_orphans", False))

    # v1.20.0 / v1.21.0 — prune, repair, and create are standalone modes: each
    # rejects co-presence with any other top-level mode (see
    # _reject_standalone_mode_conflicts). They also cannot be combined with
    # each other; prune + repair keeps its own specific message.
    if prune and repair:
        print(
            "error: --notion-prune-orphans and --notion-repair-database cannot be combined",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)
    if prune or repair:
        mode = "--notion-prune-orphans" if prune else "--notion-repair-database"
        rc = _reject_standalone_mode_conflicts(ns, mode, sibling=create)
        if rc != int(ExitCode.OK):
            return rc

    if repair:
        from aa_auto_sdr.output.notion_client_guard import resolve_notion_database_id

        db_id = resolve_notion_database_id(
            cli_override=getattr(ns, "notion_registry_database", None),
            disabled=False,
        )
        if not db_id:
            print(
                "error: --notion-repair-database requires NOTION_REGISTRY_DATABASE_ID or --notion-registry-database",
                file=sys.stderr,
            )
            return int(ExitCode.USAGE)

    # v1.21.0 — --notion-create-database is a standalone mode (see
    # _reject_standalone_mode_conflicts).
    if create:
        rc = _reject_standalone_mode_conflicts(ns, "--notion-create-database", sibling=(prune or repair))
        if rc != int(ExitCode.OK):
            return rc

    if getattr(ns, "notion_company", None) and not (in_notion_mode or repair):
        print(
            "error: --notion-company requires --format notion, --push-to-notion, or --notion-repair-database",
            file=sys.stderr,
        )
        return int(ExitCode.USAGE)

    # v1.20.0 — --yes in a pure notion-modifier context (no snapshot prune, no
    # generate) must target a destructive mode. This guard only fires when the
    # user invokes --yes alongside notion flags but without a destructive
    # notion action. It does NOT fire for --prune-snapshots --yes (snapshots
    # command handles that) or generate/batch --yes (accepted for parity).
    yes = getattr(ns, "yes", False)
    if yes and not (prune or repair or create):
        has_snapshot_prune = bool(getattr(ns, "prune_snapshots", False))
        notion_flags_only = (
            in_notion_mode
            or bool(getattr(ns, "notion_registry_database", None))
            or bool(getattr(ns, "no_notion_registry", False))
            or bool(getattr(ns, "notion_company", None))
        )
        if notion_flags_only and not has_snapshot_prune:
            print(
                "error: --yes only applies to --notion-prune-orphans, --notion-repair-database, or --notion-create-database",
                file=sys.stderr,
            )
            return int(ExitCode.USAGE)

    return int(ExitCode.OK)


def run(argv: list[str]) -> int:
    """CLI entry point.

    Order of namespace mutations (each step reads the post-step state of
    the previous one):
      1. ``parser.parse_args(argv)`` — argparse defaults applied.
      2. ``_apply_agent_mode_defaults`` — `--agent-mode` preset fills in
         `format` / `output` / `log_format` for options the user did not
         explicitly pass on argv.
      3. Validate v1.10.0 sampling flag combinations; raise
         ``SystemExit(USAGE)`` if invalid.
      4. quiet-from-output prelude — if the resolved `output` or
         `run_summary_json` targets stdout and `--quiet` was not explicit,
         flip ``ns.quiet = True`` so INFO records do not leak onto stderr
         alongside the stdout payload.
      5. ``setup_logging(ns)`` — wires console + file handlers from the
         now-final ``ns``.

    After step 4, ``ns`` is read-only by convention; downstream dispatch
    threads ``argv`` separately so per-command resolvers can re-derive
    explicit-vs-implicit decisions without re-mutating the namespace.
    """
    parser = build_parser()
    ns = parser.parse_args(argv)
    _apply_agent_mode_defaults(ns, argv, known_long_options=_configured_long_options(parser))

    # v1.10.0 — sampling flag mode-scoping. Uses raise SystemExit (not return)
    # so the exit happens before setup_logging/run_start fire — matches argparse's
    # own behavior on usage errors and keeps stderr-only output for these failures.
    # (Contrast with the retry-policy block below, which returns ExitCode.USAGE.value
    # after setup_logging has already wired handlers — that path logs run_complete.)
    is_batch = bool(getattr(ns, "batch", None)) or len(getattr(ns, "rsids", []) or []) >= 2
    if ns.sample_size is not None:
        if ns.sample_size < 1:
            print(f"error: --sample must be >= 1, got {ns.sample_size}", file=sys.stderr)
            raise SystemExit(ExitCode.USAGE.value)
        if not is_batch:
            print("error: --sample requires --batch", file=sys.stderr)
            raise SystemExit(ExitCode.USAGE.value)
    if ns.sample_seed is not None and ns.sample_size is None:
        print("error: --sample-seed requires --sample", file=sys.stderr)
        raise SystemExit(ExitCode.USAGE.value)
    if ns.sample_stratified and ns.sample_size is None:
        print("error: --sample-stratified requires --sample", file=sys.stderr)
        raise SystemExit(ExitCode.USAGE.value)

    # v1.7.0 — resolve retry policy before any auth or expensive work so
    # cross-flag errors (e.g. retry_max_delay < retry_base_delay) fail-fast
    # with USAGE rather than after a network round-trip.
    try:
        ns.retry_policy = _resolve_retry_policy(ns)
    except ValueError as e:
        # Map internal field names to user-facing flag names so the user gets
        # an actionable error without needing the library's vocabulary.
        msg = (
            str(e)
            .replace("max_delay", "--retry-max-delay")
            .replace("base_delay", "--retry-base-delay")
            .replace("max_retries", "--max-retries")
        )
        print(f"error: {msg}", file=sys.stderr)
        return ExitCode.USAGE.value
    _derive_quiet_from_output_destination(ns)
    setup_logging(ns)
    run_mode = infer_run_mode(ns)
    logger.info(
        "run_start run_mode=%s",
        run_mode,
        extra={
            "run_mode": run_mode,
            "argv_summary": _argv_summary(argv),
            "agent_mode": getattr(ns, "agent_mode", False),
        },
    )
    started = time.monotonic()
    agent_mode = getattr(ns, "agent_mode", False)
    try:
        exit_code = _dispatch(ns, parser, argv)
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.error(
            "run_failure error_class=%s",
            type(exc).__name__,
            extra={
                "exit_code": ExitCode.GENERIC.value,
                "error_class": type(exc).__name__,
                "duration_ms": duration_ms,
                "agent_mode": agent_mode,
            },
        )
        raise
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "run_complete exit_code=%s duration_ms=%s",
        exit_code,
        duration_ms,
        extra={"exit_code": exit_code, "duration_ms": duration_ms, "agent_mode": agent_mode},
    )
    return exit_code


def _dispatch(ns: argparse.Namespace, parser: argparse.ArgumentParser, argv: list[str]) -> int:
    """All command dispatch that previously lived directly in run().

    Extracted so run() can wrap it in a single try/except for run_failure
    instrumentation without proliferating log calls before every existing
    ``return X.value`` in the dispatch chain. Verbatim move — no behavior
    changes inside this helper. ``parser`` is threaded through so the
    no-args USAGE branch can still call ``parser.print_usage(sys.stderr)``."""
    rc = _validate_watch_modifiers(ns)
    if rc != int(ExitCode.OK):
        return rc

    rc = _validate_git_modifiers(ns)
    if rc != int(ExitCode.OK):
        return rc

    rc = _validate_template_modifiers(ns)
    if rc != int(ExitCode.OK):
        return rc

    rc = _validate_notion_modifiers(ns)
    if rc != int(ExitCode.OK):
        return rc

    # v1.18.0 — --push-to-notion is a top-level mode. Dispatch before any
    # generate/discovery branch so it short-circuits cleanly. Registry path
    # falls back to the input file's parent dir when --output-dir is left at
    # its default of CWD; explicit --output-dir wins.
    if getattr(ns, "push_to_notion", None):
        rc = _reject_push_to_notion_conflicts(ns)
        if rc != int(ExitCode.OK):
            return rc

        from aa_auto_sdr.cli.commands.push_to_notion import run_push_to_notion

        # Detect explicit --output-dir from argv rather than comparing the
        # resolved value to Path("."). Otherwise `--output-dir .` would be
        # indistinguishable from the parser default and the registry would be
        # written beside the input JSON instead of cwd, contradicting the
        # "explicit --output-dir wins" contract. Stop scanning at the argparse
        # end-of-options marker `--` so a literal filename "--output-dir"
        # after `--` is not mistaken for the flag.
        output_dir_explicit = False
        for tok in argv:
            if tok == "--":
                break
            if tok == "--output-dir" or tok.startswith("--output-dir="):
                output_dir_explicit = True
                break
        output_dir = getattr(ns, "output_dir", None)
        explicit_output_dir = str(output_dir) if output_dir_explicit and output_dir is not None else None
        return run_push_to_notion(
            ns.push_to_notion,
            output_dir=explicit_output_dir,
            force_new=getattr(ns, "notion_force_new", False),
            notion_registry_database=getattr(ns, "notion_registry_database", None),
            no_notion_registry=getattr(ns, "no_notion_registry", False),
            notion_company=getattr(ns, "notion_company", None),
        )

    # v1.20.0 — standalone Notion maintenance modes.
    if getattr(ns, "notion_prune_orphans", False):
        from aa_auto_sdr.cli.commands.notion_prune import run_notion_prune_orphans

        return run_notion_prune_orphans(getattr(ns, "output_dir", None), dry_run=not getattr(ns, "yes", False))

    if getattr(ns, "notion_repair_database", False):
        from aa_auto_sdr.cli.commands.notion_repair import run_notion_repair_database
        from aa_auto_sdr.output.notion_client_guard import resolve_notion_database_id

        db_id = resolve_notion_database_id(cli_override=getattr(ns, "notion_registry_database", None), disabled=False)
        return run_notion_repair_database(db_id, dry_run=not getattr(ns, "yes", False))

    if getattr(ns, "notion_create_database", False):
        from aa_auto_sdr.cli.commands.notion_create import DEFAULT_REGISTRY_TITLE, run_notion_create_database
        from aa_auto_sdr.output.notion_client_guard import resolve_notion_database_id

        already = resolve_notion_database_id(
            cli_override=getattr(ns, "notion_registry_database", None),
            disabled=False,
        )
        return run_notion_create_database(
            title=getattr(ns, "notion_database_title", None) or DEFAULT_REGISTRY_TITLE,
            dry_run=not getattr(ns, "yes", False),
            registry_already_configured=bool(already),
        )

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

    # v1.12.0 — load --quality-policy file (if any) and fill unset CLI fields
    # before any branch can read them. CLI flags always win.
    if getattr(ns, "quality_policy", None) is not None:
        from aa_auto_sdr.core.exceptions import ConfigError
        from aa_auto_sdr.sdr.quality_policy import apply_policy_defaults, load_policy

        try:
            policy = load_policy(ns.quality_policy)
        except ConfigError as e:
            print(f"error: {e}", flush=True)
            return ExitCode.CONFIG.value
        explicit = {tok.lstrip("-").replace("-", "_") for tok in argv if tok.startswith("--")}
        apply_policy_defaults(cli_namespace=ns, policy=policy, explicitly_set=explicit)
        logger.info(
            "quality_policy_loaded policy_path=%s fail_on_quality=%s quality_report=%s",
            ns.quality_policy,
            policy.fail_on_quality.value if policy.fail_on_quality else None,
            policy.quality_report,
            extra={
                "policy_path": str(ns.quality_policy),
                "fail_on_quality": policy.fail_on_quality.value if policy.fail_on_quality else None,
                "quality_report": policy.quality_report,
            },
        )

    # v1.12.0 — reject quality flags outside SDR generation (per spec §3.9).
    _non_sdr_actions = (
        getattr(ns, "stats", False),
        getattr(ns, "inventory_summary", False),
        getattr(ns, "describe_reportsuite", None),
        getattr(ns, "list_reportsuites", False),
        getattr(ns, "list_virtual_reportsuites", False),
        getattr(ns, "list_metrics", None),
        getattr(ns, "list_dimensions", None),
        getattr(ns, "list_segments", None),
        getattr(ns, "list_calculated_metrics", None),
        getattr(ns, "list_classification_datasets", None),
        getattr(ns, "diff", None),
    )
    _quality_flags_set = bool(
        getattr(ns, "fail_on_quality", None)
        or getattr(ns, "quality_report", None)
        or getattr(ns, "quality_policy", None),
    )
    if any(_non_sdr_actions) and _quality_flags_set:
        print(
            "error: --quality-report / --quality-policy / --fail-on-quality require "
            "single-RSID or --batch SDR generation; not valid with list/inspect/diff actions.",
            flush=True,
        )
        return ExitCode.USAGE.value

    _apply_quality_auto_enable(ns)

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

    # v1.11.0 — inventory-summary action
    if ns.inventory_summary:
        from aa_auto_sdr.cli.commands import inventory as inventory_cmd

        return inventory_cmd.run(
            rsids=rsids,
            profile=ns.profile,
            format_name=ns.format,
            retry_policy=ns.retry_policy,
            name_match=ns.name_match,
        )

    # v1.13.0 — trending-window action
    if ns.trending_window:
        from aa_auto_sdr.cli.commands import trending as trending_cmd

        # `ns.ignore_fields` is a CSV string (parser stores it as-is); split
        # before passing to the trending handler so we get field names, not
        # individual characters. Mirrors the --diff branch's pattern.
        ignore = tuple(f.strip() for f in (ns.ignore_fields or "").split(",") if f.strip())
        return trending_cmd.run(
            rsids=rsids,
            duration=ns.trending_window,
            snapshot_dir=ns.snapshot_dir,
            profile=ns.profile,
            format_name=ns.format,
            output=ns.output,
            extended_fields=ns.extended_fields,
            ignore_fields=ignore,
        )

    # v1.14.0 — watch action
    if getattr(ns, "watch", False):
        from aa_auto_sdr.cli.commands import watch as watch_cmd

        return watch_cmd.run(ns)

    # v1.13.0 — compare-with-prev action (sugar over --diff)
    if ns.compare_with_prev:
        from aa_auto_sdr.cli.commands import compare_with_prev as compare_cmd

        # Mirror the --diff branch's argument shaping (see line ~537 below)
        # so compare_with_prev → diff_cmd.run gets identical inputs.
        # ignore_fields / show_only are CSV strings on the namespace; split
        # before frozenset construction (otherwise we get a frozenset of
        # characters). diff_labels is a 2-tuple of "A=baseline"/"B=candidate"
        # strings; reverse_diff is the actual flag (not "reverse").
        ignore = frozenset(f.strip() for f in (ns.ignore_fields or "").split(",") if f.strip())
        show_only = frozenset(t.strip() for t in (ns.show_only or "").split(",") if t.strip())
        labels: tuple[str, str] | None = None
        if ns.diff_labels:
            a_label = ns.diff_labels[0].split("=", 1)[-1]
            b_label = ns.diff_labels[1].split("=", 1)[-1]
            labels = (a_label, b_label)
        return compare_cmd.run(
            rsids=rsids,
            profile=ns.profile,
            snapshot_dir=resolve_snapshot_dir(ns),
            format_name=ns.format,
            output=ns.output,
            side_by_side=ns.side_by_side,
            summary=ns.summary,
            ignore_fields=ignore,
            extended_fields=ns.extended_fields,
            quiet=ns.quiet_diff,
            labels=labels,
            reverse=ns.reverse_diff,
            changes_only=ns.changes_only,
            show_only=show_only,
            max_issues=ns.max_issues,
            warn_threshold=ns.warn_threshold,
            color_theme=ns.color_theme,
        )

    # v1.2 — stats action
    if ns.stats:
        from aa_auto_sdr.cli.commands import stats as stats_cmd

        return stats_cmd.run(
            rsids=rsids,
            profile=ns.profile,
            format_name=ns.format,
            retry_policy=ns.retry_policy,
            name_match=ns.name_match,
        )

    # v1.2 — interactive action
    if ns.interactive:
        from aa_auto_sdr.cli.commands import interactive as interactive_cmd

        return interactive_cmd.run(profile=ns.profile, retry_policy=ns.retry_policy)

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

        # Pass raw ns.snapshot_dir (not resolve_snapshot_dir) so the
        # "requires --profile or --snapshot-dir" guard inside list_run
        # can fire when the user sets neither.
        return snap_cmd.list_run(
            profile=ns.profile,
            rsid=rsids[0] if rsids else None,
            format_name=ns.format,
            snapshot_dir=ns.snapshot_dir,
        )
    if ns.prune_snapshots:
        if len(rsids) > 1:
            print(
                "error: --prune-snapshots accepts at most one positional <RSID> filter",
                flush=True,
            )
            return ExitCode.USAGE.value
        from aa_auto_sdr.cli.commands import snapshots as snap_cmd

        # Pass raw ns.snapshot_dir (not resolve_snapshot_dir) so the
        # "requires --profile or --snapshot-dir" guard inside prune_run
        # can fire when the user sets neither.
        return snap_cmd.prune_run(
            profile=ns.profile,
            rsid=rsids[0] if rsids else None,
            keep_last=ns.keep_last,
            keep_since=ns.keep_since,
            dry_run=ns.dry_run,
            assume_yes=ns.yes,
            snapshot_dir=ns.snapshot_dir,
        )

    # v1.1 — profile commands
    if ns.profile_list:
        from aa_auto_sdr.cli.commands import profiles as prof_cmd

        return prof_cmd.list_run(format_name=ns.format)
    if ns.profile_test:
        from aa_auto_sdr.cli.commands import profiles as prof_cmd

        return prof_cmd.test_run(ns.profile_test, retry_policy=ns.retry_policy)
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

        resolved_output = resolve_agent_output_path(
            ns,
            argv=argv,
            output_format=(ns.format or "json"),
            stdout_formats=DISCOVERY_STDOUT_FORMATS,
        )
        return discovery_cmd.run_list_reportsuites(
            profile=ns.profile,
            format_name=ns.format,
            output=resolved_output,
            name_filter=ns.filter,
            name_exclude=ns.exclude,
            sort_field=ns.sort,
            limit=ns.limit,
            retry_policy=ns.retry_policy,
        )
    if ns.list_virtual_reportsuites:
        from aa_auto_sdr.cli.commands import discovery as discovery_cmd

        resolved_output = resolve_agent_output_path(
            ns,
            argv=argv,
            output_format=(ns.format or "json"),
            stdout_formats=DISCOVERY_STDOUT_FORMATS,
        )
        return discovery_cmd.run_list_virtual_reportsuites(
            profile=ns.profile,
            format_name=ns.format,
            output=resolved_output,
            name_filter=ns.filter,
            name_exclude=ns.exclude,
            sort_field=ns.sort,
            limit=ns.limit,
            retry_policy=ns.retry_policy,
        )
    if ns.describe_reportsuite:
        from aa_auto_sdr.cli.commands import inspect as inspect_cmd

        resolved_output = resolve_agent_output_path(
            ns,
            argv=argv,
            output_format=(ns.format or "json"),
            stdout_formats=DISCOVERY_STDOUT_FORMATS,
        )
        return inspect_cmd.run_describe_reportsuite(
            identifier=ns.describe_reportsuite,
            profile=ns.profile,
            format_name=ns.format,
            output=resolved_output,
            retry_policy=ns.retry_policy,
            name_match=ns.name_match,
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
            resolved_output = resolve_agent_output_path(
                ns,
                argv=argv,
                output_format=(ns.format or "json"),
                stdout_formats=DISCOVERY_STDOUT_FORMATS,
            )
            return handler(
                identifier=identifier,
                profile=ns.profile,
                format_name=ns.format,
                output=resolved_output,
                name_filter=ns.filter,
                name_exclude=ns.exclude,
                sort_field=ns.sort,
                limit=ns.limit,
                retry_policy=ns.retry_policy,
                name_match=ns.name_match,
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
        fmt_for_resolve = ns.format or "console"
        resolved_output = resolve_agent_output_path(
            ns,
            argv=argv,
            output_format=fmt_for_resolve,
            stdout_formats=DIFF_STDOUT_FORMATS,
        )
        # NOTE: ``diff_cmd.run``'s ``quiet=`` is the *renderer-level* "drop
        # unchanged trailers" flag — distinct from the *logger-level* quiet
        # that the prelude in ``run()`` already applied to ``ns.quiet`` for
        # stdout-bound runs. Don't conflate them: pass only ``ns.quiet_diff``.
        return diff_cmd.run(
            a=ns.diff[0],
            b=ns.diff[1],
            format_name=ns.format,
            output=resolved_output,
            profile=ns.profile,
            snapshot_dir=resolve_snapshot_dir(ns),
            side_by_side=ns.side_by_side,
            summary=ns.summary,
            ignore_fields=ignore,
            extended_fields=ns.extended_fields,
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
        resolved_output = resolve_agent_output_path(
            ns,
            argv=argv,
            output_format=(ns.format or "excel"),
            stdout_formats=frozenset(),
        )
        if resolved_output == "-":
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
            retry_policy=ns.retry_policy,
            workers=ns.workers,
            fail_fast=ns.fail_fast,
            enable_cache=ns.enable_cache,
            clear_cache=ns.clear_cache,
            cache_ttl=ns.cache_ttl,
            cache_size=ns.cache_size,
            audit_naming=ns.audit_naming,
            flag_stale=ns.flag_stale,
            name_match=ns.name_match,
            sample_size=ns.sample_size,
            sample_seed=ns.sample_seed,
            sample_stratified=ns.sample_stratified,
            fail_on_quality=ns.fail_on_quality,
            quality_report=ns.quality_report,
            git_commit=getattr(ns, "git_commit", False),
            git_push=getattr(ns, "git_push", False),
            git_message=getattr(ns, "git_message", None),
            template_path=getattr(ns, "template", None),
            template_organization=getattr(ns, "template_organization", None),
            snapshot_dir=resolve_snapshot_dir(ns),
            notion_force_new=getattr(ns, "notion_force_new", False),
            notion_registry_database=getattr(ns, "notion_registry_database", None),
            no_notion_registry=getattr(ns, "no_notion_registry", False),
            notion_company=getattr(ns, "notion_company", None),
        )

    # Single identifier → generate. Default --format to "excel" if omitted.
    resolved_output = resolve_agent_output_path(
        ns,
        argv=argv,
        output_format=(ns.format or "excel"),
        stdout_formats=frozenset(),
    )
    output_dir: Path = Path("-") if resolved_output == "-" else ns.output_dir
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
        retry_policy=ns.retry_policy,
        audit_naming=ns.audit_naming,
        flag_stale=ns.flag_stale,
        name_match=ns.name_match,
        fail_on_quality=ns.fail_on_quality,
        quality_report=ns.quality_report,
        git_commit=getattr(ns, "git_commit", False),
        git_push=getattr(ns, "git_push", False),
        git_message=getattr(ns, "git_message", None),
        template_path=getattr(ns, "template", None),
        template_organization=getattr(ns, "template_organization", None),
        snapshot_dir=resolve_snapshot_dir(ns),
        notion_force_new=getattr(ns, "notion_force_new", False),
        notion_registry_database=getattr(ns, "notion_registry_database", None),
        no_notion_registry=getattr(ns, "no_notion_registry", False),
        notion_company=getattr(ns, "notion_company", None),
    )


def _stub_action(name: str) -> int:
    print(f"error: {name} not yet implemented in this build", flush=True)
    return ExitCode.GENERIC.value
