"""Argparse surface for v0.3: action flags, filter/exclude/sort/limit, format, output."""

import pytest

from aa_auto_sdr.cli.parser import build_parser


def test_positional_rsid() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod"])
    assert ns.rsid == "demo.prod"


def test_format_default_is_none() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod"])
    assert ns.format is None


def test_output_dir_default_is_dot() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod"])
    assert str(ns.output_dir) == "."


def test_profile_add_is_action() -> None:
    p = build_parser()
    ns = p.parse_args(["--profile-add", "prod"])
    assert ns.profile_add == "prod"


def test_profile_add_is_mutually_exclusive_with_rsid() -> None:
    """v0.1 defines --profile-add as a standalone action — RSID not required."""
    p = build_parser()
    ns = p.parse_args(["--profile-add", "prod"])
    assert ns.rsid is None


def test_show_config_is_action() -> None:
    p = build_parser()
    ns = p.parse_args(["--show-config"])
    assert ns.show_config is True
    assert ns.rsid is None


def test_profile_flag() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod", "--profile", "prod"])
    assert ns.profile == "prod"


def test_list_reportsuites_flag_parses() -> None:
    p = build_parser()
    ns = p.parse_args(["--list-reportsuites"])
    assert ns.list_reportsuites is True
    assert ns.rsid is None


def test_list_virtual_reportsuites_flag_parses() -> None:
    p = build_parser()
    ns = p.parse_args(["--list-virtual-reportsuites"])
    assert ns.list_virtual_reportsuites is True


def test_describe_reportsuite_with_arg_parses() -> None:
    p = build_parser()
    ns = p.parse_args(["--describe-reportsuite", "demo.prod"])
    assert ns.describe_reportsuite == "demo.prod"


def test_list_metrics_with_arg_parses() -> None:
    p = build_parser()
    ns = p.parse_args(["--list-metrics", "demo.prod"])
    assert ns.list_metrics == "demo.prod"


def test_list_dimensions_segments_calcmetrics_classifications_parse() -> None:
    p = build_parser()
    for flag, attr in [
        ("--list-dimensions", "list_dimensions"),
        ("--list-segments", "list_segments"),
        ("--list-calculated-metrics", "list_calculated_metrics"),
        ("--list-classification-datasets", "list_classification_datasets"),
    ]:
        ns = p.parse_args([flag, "demo.prod"])
        assert getattr(ns, attr) == "demo.prod"


def test_filter_exclude_sort_limit_parse() -> None:
    p = build_parser()
    ns = p.parse_args(
        [
            "--list-metrics",
            "demo.prod",
            "--filter",
            "page",
            "--exclude",
            "test",
            "--sort",
            "name",
            "--limit",
            "10",
        ]
    )
    assert ns.filter == "page"
    assert ns.exclude == "test"
    assert ns.sort == "name"
    assert ns.limit == 10


def test_output_flag_parses_dash() -> None:
    p = build_parser()
    ns = p.parse_args(["--list-metrics", "demo.prod", "--output", "-"])
    assert ns.output == "-"


def test_output_flag_parses_path() -> None:
    p = build_parser()
    ns = p.parse_args(["--list-metrics", "demo.prod", "--output", "/tmp/out.json"])
    assert ns.output == "/tmp/out.json"


def test_action_flags_mutually_exclusive() -> None:
    """Two action flags in one invocation should error out."""
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--list-reportsuites", "--show-config"])


def test_format_flag_accepts_any_string_at_parse_time() -> None:
    """The parser doesn't restrict --format choices — handlers do, since
    different actions have different allowlists."""
    p = build_parser()
    ns = p.parse_args(["--list-metrics", "demo.prod", "--format", "json"])
    assert ns.format == "json"
    ns = p.parse_args(["demo.prod", "--format", "excel"])
    assert ns.format == "excel"


def test_batch_flag_parses_multiple_rsids() -> None:
    p = build_parser()
    ns = p.parse_args(["--batch", "rs1", "rs2", "rs3"])
    assert ns.batch == ["rs1", "rs2", "rs3"]
    assert ns.rsid is None


def test_batch_flag_requires_at_least_one_arg() -> None:
    """nargs="+" → bare `--batch` is a usage error."""
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--batch"])


def test_batch_accepts_quoted_names() -> None:
    p = build_parser()
    ns = p.parse_args(["--batch", "Adobe Store", "rs2"])
    assert ns.batch == ["Adobe Store", "rs2"]


def test_batch_mutually_exclusive_with_list_reportsuites() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--batch", "rs1", "--list-reportsuites"])


def test_batch_with_format_and_output_dir() -> None:
    p = build_parser()
    ns = p.parse_args(["--batch", "rs1", "rs2", "--format", "json", "--output-dir", "/tmp/out"])
    assert ns.batch == ["rs1", "rs2"]
    assert ns.format == "json"
    # as_posix() for cross-platform: Path repr is "\\tmp\\out" on Windows, "/tmp/out" on POSIX
    assert ns.output_dir.as_posix() == "/tmp/out"


def test_snapshot_flag_parses() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod", "--snapshot"])
    assert ns.snapshot is True


def test_snapshot_default_false() -> None:
    p = build_parser()
    ns = p.parse_args(["demo.prod"])
    assert ns.snapshot is False


def test_snapshot_with_batch() -> None:
    p = build_parser()
    ns = p.parse_args(["--batch", "rs1", "rs2", "--snapshot", "--profile", "prod"])
    assert ns.snapshot is True
    assert ns.batch == ["rs1", "rs2"]
    assert ns.profile == "prod"


def test_diff_flag_parses_two_args() -> None:
    p = build_parser()
    ns = p.parse_args(["--diff", "a.json", "b.json"])
    assert ns.diff == ["a.json", "b.json"]


def test_diff_requires_exactly_two_args() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--diff", "only-one.json"])


def test_diff_mutually_exclusive_with_batch() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--diff", "a", "b", "--batch", "rs1"])


def test_exit_codes_flag_parses() -> None:
    p = build_parser()
    ns = p.parse_args(["--exit-codes"])
    assert ns.exit_codes is True


def test_explain_exit_code_with_int_arg() -> None:
    p = build_parser()
    ns = p.parse_args(["--explain-exit-code", "11"])
    assert ns.explain_exit_code == 11


def test_explain_exit_code_with_invalid_arg_errors() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--explain-exit-code", "not-a-number"])


def test_exit_codes_mutex_with_diff() -> None:
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["--exit-codes", "--diff", "a", "b"])


class TestV11Flags:
    def test_list_snapshots_action(self) -> None:
        ns = build_parser().parse_args(["--list-snapshots"])
        assert ns.list_snapshots is True

    def test_prune_snapshots_with_keep_last(self) -> None:
        ns = build_parser().parse_args(["--prune-snapshots", "--keep-last", "5"])
        assert ns.prune_snapshots is True
        assert ns.keep_last == 5

    def test_keep_last_keep_since_mutex(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args(
                ["--prune-snapshots", "--keep-last", "5", "--keep-since", "30d"],
            )

    def test_profile_list(self) -> None:
        ns = build_parser().parse_args(["--profile-list"])
        assert ns.profile_list is True

    def test_profile_test(self) -> None:
        ns = build_parser().parse_args(["--profile-test", "prod"])
        assert ns.profile_test == "prod"

    def test_profile_import(self) -> None:
        ns = build_parser().parse_args(["--profile-import", "prod", "/tmp/x.json"])
        assert ns.profile_import == ["prod", "/tmp/x.json"]

    def test_auto_snapshot(self) -> None:
        ns = build_parser().parse_args(["RS1", "--auto-snapshot"])
        assert ns.auto_snapshot is True

    def test_diff_format_pr_comment(self) -> None:
        ns = build_parser().parse_args(
            ["--diff", "a.json", "b.json", "--format", "pr-comment"],
        )
        assert ns.format == "pr-comment"

    def test_side_by_side_summary_ignore_fields(self) -> None:
        ns = build_parser().parse_args(
            ["--diff", "a.json", "b.json", "--side-by-side", "--summary", "--ignore-fields", "description,tags"],
        )
        assert ns.side_by_side is True
        assert ns.summary is True
        assert ns.ignore_fields == "description,tags"

    def test_dry_run(self) -> None:
        ns = build_parser().parse_args(
            ["--prune-snapshots", "--keep-last", "5", "--dry-run"],
        )
        assert ns.dry_run is True
