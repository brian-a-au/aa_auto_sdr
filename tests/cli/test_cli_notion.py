"""Tests for Notion-related CLI flag wiring."""

from __future__ import annotations

from argparse import Namespace

from aa_auto_sdr.cli.main import _dispatch, _resolve_retry_policy, _validate_notion_modifiers
from aa_auto_sdr.cli.parser import build_parser
from aa_auto_sdr.core.exit_codes import ExitCode


def _parse(args):
    return build_parser().parse_args(args)


def test_format_notion_accepted():
    ns = _parse(["examplersid1", "--format", "notion"])
    assert ns.format == "notion"


def test_notion_force_new_default_false():
    ns = _parse(["examplersid1", "--format", "notion"])
    assert ns.notion_force_new is False


def test_notion_force_new_sets_true():
    ns = _parse(["examplersid1", "--format", "notion", "--notion-force-new"])
    assert ns.notion_force_new is True


def test_push_to_notion_default_none():
    ns = _parse(["examplersid1"])
    assert ns.push_to_notion is None


def test_push_to_notion_accepts_file():
    ns = _parse(["--push-to-notion", "./reports/sdr.json"])
    assert ns.push_to_notion == "./reports/sdr.json"


def test_push_to_notion_with_force_new():
    ns = _parse(["--push-to-notion", "./reports/sdr.json", "--notion-force-new"])
    assert ns.push_to_notion == "./reports/sdr.json"
    assert ns.notion_force_new is True


# --- _validate_notion_modifiers unit + dispatch tests ---


def test_validate_notion_modifiers_ok_when_format_not_notion():
    ns = Namespace(format="excel", watch=True, batch=None, workers=4)
    assert _validate_notion_modifiers(ns) == int(ExitCode.OK)


def test_validate_notion_modifiers_ok_for_simple_notion():
    ns = Namespace(format="notion", watch=False, batch=None, workers=1)
    assert _validate_notion_modifiers(ns) == int(ExitCode.OK)


def test_validate_notion_modifiers_watch_now_allowed():
    # v1.20.0: --watch --format notion is no longer rejected by the validator.
    ns = Namespace(
        format="notion",
        watch=True,
        batch=None,
        workers=1,
        notion_prune_orphans=False,
        notion_repair_database=False,
        notion_registry_database=None,
        no_notion_registry=False,
        notion_company=None,
        yes=False,
        push_to_notion=None,
        rsids=[],
        diff=None,
        prune_snapshots=False,
    )
    assert _validate_notion_modifiers(ns) == int(ExitCode.OK)


def test_validate_notion_modifiers_workers_gt_1_now_allowed():
    # v1.20.0: --workers > 1 with --format notion is no longer rejected.
    ns = Namespace(
        format="notion",
        watch=False,
        batch=["r1", "r2"],
        workers=4,
        rsids=[],
        notion_prune_orphans=False,
        notion_repair_database=False,
        notion_registry_database=None,
        no_notion_registry=False,
        notion_company=None,
        yes=False,
        push_to_notion=None,
        diff=None,
        prune_snapshots=False,
    )
    assert _validate_notion_modifiers(ns) == int(ExitCode.OK)


def test_validate_notion_modifiers_positional_batch_workers_gt_1_now_allowed():
    # v1.20.0: multi-positional batch + --workers 4 + --format notion now allowed.
    ns = Namespace(
        format="notion",
        watch=False,
        batch=None,
        workers=4,
        rsids=["r1", "r2"],
        notion_prune_orphans=False,
        notion_repair_database=False,
        notion_registry_database=None,
        no_notion_registry=False,
        notion_company=None,
        yes=False,
        push_to_notion=None,
        diff=None,
        prune_snapshots=False,
    )
    assert _validate_notion_modifiers(ns) == int(ExitCode.OK)


def test_positional_batch_notion_workers_gt_1_now_allowed_in_dispatch(capsys, monkeypatch):
    # v1.20.0: dispatch no longer rejects this combination at the validator level.
    # It will reach batch.run which needs auth — monkeypatch to avoid that.
    import aa_auto_sdr.cli.commands.batch as batch_mod

    monkeypatch.setattr(batch_mod, "run", lambda **_kw: 0)
    argv = ["rsid1", "rsid2", "--format", "notion", "--workers", "4"]
    parser = build_parser()
    ns = parser.parse_args(argv)
    ns.retry_policy = _resolve_retry_policy(ns)
    _dispatch(ns, parser, argv)
    err = capsys.readouterr().err
    # Must not contain the old rejection message
    assert "is not supported with --format notion" not in err


# --- --push-to-notion co-presence rejection ---


def test_push_to_notion_with_diff_rejected(tmp_path, capsys):
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["--push-to-notion", str(p), "--diff", "a.json", "b.json"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "--diff" in capsys.readouterr().err


def test_push_to_notion_with_batch_rejected(tmp_path, capsys):
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["--push-to-notion", str(p), "--batch", "rsid1", "rsid2"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "--batch" in capsys.readouterr().err


def test_push_to_notion_with_positional_rsid_rejected(tmp_path, capsys):
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["rsid1", "--push-to-notion", str(p)])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "positional rsid" in capsys.readouterr().err.lower()


def test_push_to_notion_with_list_reportsuites_rejected(tmp_path, capsys):
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["--push-to-notion", str(p), "--list-reportsuites"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "--list-reportsuites" in capsys.readouterr().err


def test_push_to_notion_with_validate_config_rejected(tmp_path, capsys):
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["--push-to-notion", str(p), "--validate-config"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "--validate-config" in capsys.readouterr().err


def test_push_to_notion_with_config_status_rejected(tmp_path, capsys):
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["--push-to-notion", str(p), "--config-status"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "--config-status" in capsys.readouterr().err


def test_push_to_notion_with_interactive_rejected(tmp_path, capsys):
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["--push-to-notion", str(p), "--interactive"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "--interactive" in capsys.readouterr().err


def test_push_to_notion_with_profile_list_rejected(tmp_path, capsys):
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["--push-to-notion", str(p), "--profile-list"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "--profile-list" in capsys.readouterr().err


def test_push_to_notion_with_exit_codes_rejected(tmp_path, capsys):
    # --exit-codes only fast-paths when argv[0]; when it appears after
    # --push-to-notion, dispatch must reject the combination rather than let
    # push silently win.
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["--push-to-notion", str(p), "--exit-codes"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "--exit-codes" in capsys.readouterr().err


def test_push_to_notion_with_explain_exit_code_rejected(tmp_path, capsys):
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["--push-to-notion", str(p), "--explain-exit-code", "17"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "--explain-exit-code" in capsys.readouterr().err


def test_push_to_notion_with_explain_exit_code_zero_rejected(tmp_path, capsys):
    # ExitCode.OK == 0 is a legitimate --explain-exit-code argument; int(0) is
    # falsy, so a naive truthiness check on the conflict list would let push
    # silently win for this one value. Verify the guard uses an explicit
    # None check for this attr.
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["--push-to-notion", str(p), "--explain-exit-code", "0"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "--explain-exit-code" in capsys.readouterr().err


def test_push_to_notion_with_completion_rejected(tmp_path, capsys):
    parser = build_parser()
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    ns = parser.parse_args(["--push-to-notion", str(p), "--completion", "bash"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "--completion" in capsys.readouterr().err


# --- explicit --output-dir wins (argv-based detection) ---


def _run_dispatch_capturing_output_dir(argv, monkeypatch):
    """Helper: parse argv and dispatch, capturing the output_dir kw passed
    to run_push_to_notion. Returns (rc, captured_output_dir).

    Uses monkeypatch.setattr so teardown is automatic even if the dispatch
    raises before the original would be restored manually.
    """
    import aa_auto_sdr.cli.commands.push_to_notion as pt_mod

    parser = build_parser()
    ns = parser.parse_args(argv)
    captured = {}

    def fake_run(json_path, output_dir=None, force_new=False, **kwargs):
        captured["output_dir"] = output_dir
        return 0

    monkeypatch.setattr(pt_mod, "run_push_to_notion", fake_run)
    rc = _dispatch(ns, parser, argv)
    return rc, captured.get("output_dir")


def test_push_to_notion_default_output_dir_is_implicit(tmp_path, monkeypatch):
    # No --output-dir on argv → caller receives None so the command falls
    # back to the input file's parent dir.
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    rc, captured = _run_dispatch_capturing_output_dir(["--push-to-notion", str(p)], monkeypatch)
    assert rc == 0
    assert captured is None


def test_push_to_notion_explicit_output_dir_dot_is_honored(tmp_path, monkeypatch):
    # `--output-dir .` matches the parser default by value, but the user
    # explicitly asked for cwd. Detection must be argv-based, not value-based,
    # so the explicit "." is forwarded.
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    rc, captured = _run_dispatch_capturing_output_dir(["--push-to-notion", str(p), "--output-dir", "."], monkeypatch)
    assert rc == 0
    assert captured == "."


def test_push_to_notion_explicit_output_dir_equals_form_is_honored(tmp_path, monkeypatch):
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    rc, captured = _run_dispatch_capturing_output_dir(["--push-to-notion", str(p), "--output-dir=./out"], monkeypatch)
    assert rc == 0
    assert captured == "out"


def test_push_to_notion_explicit_output_dir_non_default_value(tmp_path, monkeypatch):
    p = tmp_path / "sdr.json"
    p.write_text("{}")
    target = tmp_path / "elsewhere"
    rc, captured = _run_dispatch_capturing_output_dir(
        ["--push-to-notion", str(p), "--output-dir", str(target)], monkeypatch
    )
    assert rc == 0
    assert captured == str(target)


def test_watch_notion_no_longer_rejected_in_dispatch(capsys, monkeypatch):
    # v1.20.0: --watch --format notion passes the validator; watch command handles it.
    import aa_auto_sdr.cli.commands.watch as watch_mod

    monkeypatch.setattr(watch_mod, "run", lambda _ns: 0)
    argv = ["examplersid1", "--watch", "--interval", "1m", "--format", "notion"]
    parser = build_parser()
    ns = parser.parse_args(argv)
    ns.retry_policy = _resolve_retry_policy(ns)
    _dispatch(ns, parser, argv)
    err = capsys.readouterr().err
    assert "not supported with --format notion" not in err


def test_batch_notion_workers_gt_1_no_longer_rejected_in_dispatch(capsys, monkeypatch):
    # v1.20.0: batch with --workers > 1 and --format notion is no longer rejected.
    import aa_auto_sdr.cli.commands.batch as batch_mod

    monkeypatch.setattr(batch_mod, "run", lambda **_kw: 0)
    argv = ["--batch", "rsid1", "rsid2", "--format", "notion", "--workers", "4"]
    parser = build_parser()
    ns = parser.parse_args(argv)
    ns.retry_policy = _resolve_retry_policy(ns)
    _dispatch(ns, parser, argv)
    err = capsys.readouterr().err.lower()
    assert "is not supported with --format notion" not in err


# --- v1.19.0: registry-database flags ---


def test_parser_accepts_notion_registry_database():
    ns = build_parser().parse_args(["examplersid1", "--format", "notion", "--notion-registry-database", "db-id"])
    assert ns.notion_registry_database == "db-id"


def test_parser_accepts_no_notion_registry():
    ns = build_parser().parse_args(["examplersid1", "--format", "notion", "--no-notion-registry"])
    assert ns.no_notion_registry is True


def test_parser_defaults_for_new_flags():
    ns = build_parser().parse_args(["examplersid1"])
    assert ns.notion_registry_database is None
    assert ns.no_notion_registry is False


# --- v1.19.0: cross-flag rejections ---
#
# These call `_dispatch` directly (like the sibling dispatch tests above)
# rather than `run()`. `run()` initializes global logging handlers bound to
# the active stream; under capsys that stream is torn down after the test,
# and a later test's log emit then errors and corrupts its stderr capture.
# `_dispatch` exercises the same validator (cli/main.py line ~460) without
# that global side effect.


def test_dispatch_rejects_database_and_no_registry_together(capsys):
    parser = build_parser()
    ns = parser.parse_args(
        [
            "examplersid1",
            "--format",
            "notion",
            "--notion-registry-database",
            "db-id",
            "--no-notion-registry",
        ]
    )
    rc = _dispatch(ns, parser, [])
    err = capsys.readouterr().err
    assert rc == int(ExitCode.USAGE)
    assert "--no-notion-registry" in err
    assert "--notion-registry-database" in err


def test_dispatch_rejects_database_flag_without_notion_mode(capsys):
    parser = build_parser()
    ns = parser.parse_args(
        [
            "examplersid1",
            "--format",
            "json",
            "--notion-registry-database",
            "db-id",
        ]
    )
    rc = _dispatch(ns, parser, [])
    err = capsys.readouterr().err
    assert rc == int(ExitCode.USAGE)
    assert "--notion-registry-database" in err


def test_dispatch_rejects_no_registry_without_notion_mode(capsys):
    parser = build_parser()
    ns = parser.parse_args(
        [
            "examplersid1",
            "--format",
            "json",
            "--no-notion-registry",
        ]
    )
    rc = _dispatch(ns, parser, [])
    err = capsys.readouterr().err
    assert rc == int(ExitCode.USAGE)
    assert "--no-notion-registry" in err


# --- v1.20.0: relaxed watch/parallel rejections ---


def test_watch_notion_now_allowed(capsys):
    # --watch --format notion no longer a USAGE error at validation time.
    # The old "not supported with --format notion" message must be gone.
    parser = build_parser()
    ns = parser.parse_args(["examplersid1", "--watch", "--interval", "1h", "--format", "notion"])
    # Don't dispatch (watch would loop); just validate the notion modifiers directly.
    rc = _validate_notion_modifiers(ns)
    err = capsys.readouterr().err
    assert "not supported with --format notion" not in err
    # rc may be OK or USAGE for unrelated reasons — we only care the old message is gone.
    _ = rc  # silence unused-variable linters


def test_parallel_batch_notion_now_allowed(capsys):
    # Multi-RSID batch with --workers 2 + --format notion no longer rejected by
    # _validate_notion_modifiers. (Downstream dispatch still validates combinations.)
    parser = build_parser()
    ns = parser.parse_args(["rs1", "rs2", "--format", "notion", "--workers", "2"])
    rc = _validate_notion_modifiers(ns)
    err = capsys.readouterr().err
    assert "is not supported with --format notion" not in err
    _ = rc


# --- v1.20.0: new flag parser tests ---


def test_parser_accepts_notion_prune_orphans():
    ns = build_parser().parse_args(["--notion-prune-orphans"])
    assert ns.notion_prune_orphans is True


def test_parser_default_notion_prune_orphans_false():
    ns = build_parser().parse_args(["examplersid1"])
    assert ns.notion_prune_orphans is False


def test_parser_accepts_notion_repair_database():
    ns = build_parser().parse_args(["--notion-repair-database"])
    assert ns.notion_repair_database is True


def test_parser_default_notion_repair_database_false():
    ns = build_parser().parse_args(["examplersid1"])
    assert ns.notion_repair_database is False


def test_parser_accepts_notion_company():
    ns = build_parser().parse_args(["examplersid1", "--format", "notion", "--notion-company", "acme"])
    assert ns.notion_company == "acme"


def test_parser_default_notion_company_none():
    ns = build_parser().parse_args(["examplersid1"])
    assert ns.notion_company is None


def test_parser_yes_flag_existing():
    # --yes already existed; ensure it still works (dest="yes")
    ns = build_parser().parse_args(["examplersid1", "--prune-snapshots", "--yes"])
    assert ns.yes is True


# --- v1.20.0: new validator rules ---


def test_company_without_notion_mode_rejected(capsys):
    # --notion-company without --format notion / --push-to-notion / --notion-repair-database → USAGE
    parser = build_parser()
    ns = parser.parse_args(["rs1", "--notion-company", "acme"])
    rc = _dispatch(ns, parser, [])
    err = capsys.readouterr().err
    assert rc == int(ExitCode.USAGE)
    assert "--notion-company" in err


def test_prune_with_generation_rejected(capsys):
    # --notion-prune-orphans combined with a positional RSID (generation) → USAGE
    parser = build_parser()
    ns = parser.parse_args(["rs1", "--notion-prune-orphans"])
    rc = _dispatch(ns, parser, [])
    err = capsys.readouterr().err
    assert rc == int(ExitCode.USAGE)
    assert "--notion-prune-orphans" in err


def test_repair_without_database_id_rejected(capsys, monkeypatch):
    # --notion-repair-database without env var or --notion-registry-database → USAGE
    monkeypatch.delenv("NOTION_REGISTRY_DATABASE_ID", raising=False)
    parser = build_parser()
    ns = parser.parse_args(["--notion-repair-database"])
    rc = _dispatch(ns, parser, [])
    err = capsys.readouterr().err
    assert rc == int(ExitCode.USAGE)
    assert "NOTION_REGISTRY_DATABASE_ID" in err or "--notion-repair-database" in err


def test_yes_with_notion_mode_but_no_destructive_action_rejected(capsys):
    # --yes with --format notion but without --notion-prune-orphans or
    # --notion-repair-database → USAGE (notion context without destructive target)
    parser = build_parser()
    ns = parser.parse_args(["rs1", "--format", "notion", "--yes"])
    rc = _dispatch(ns, parser, [])
    err = capsys.readouterr().err
    assert rc == int(ExitCode.USAGE)
    assert "--yes" in err


def test_prune_and_repair_combined_rejected(capsys):
    # --notion-prune-orphans and --notion-repair-database together → USAGE
    parser = build_parser()
    ns = parser.parse_args(["--notion-prune-orphans", "--notion-repair-database"])
    rc = _dispatch(ns, parser, [])
    capsys.readouterr()
    assert rc == int(ExitCode.USAGE)


def test_repair_with_database_id_flag_ok(capsys, monkeypatch):
    # --notion-repair-database with --notion-registry-database → should not fail on missing db id
    monkeypatch.delenv("NOTION_REGISTRY_DATABASE_ID", raising=False)
    parser = build_parser()
    ns = parser.parse_args(["--notion-repair-database", "--notion-registry-database", "some-db-id"])
    rc = _validate_notion_modifiers(ns)
    # Should not return USAGE for missing db id since we supplied one via flag
    assert rc != int(ExitCode.USAGE) or "NOTION_REGISTRY_DATABASE_ID" not in capsys.readouterr().err
