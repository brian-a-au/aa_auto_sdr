"""Tests for Notion-related CLI flag wiring."""

from __future__ import annotations

from argparse import Namespace

from aa_auto_sdr.cli.main import _dispatch, _validate_notion_modifiers
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


def test_validate_notion_modifiers_rejects_watch():
    ns = Namespace(format="notion", watch=True, batch=None, workers=1)
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_validate_notion_modifiers_rejects_workers_gt_1():
    ns = Namespace(format="notion", watch=False, batch=["r1", "r2"], workers=4, rsids=[])
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_validate_notion_modifiers_rejects_positional_batch_workers_gt_1():
    # Multi-positional shorthand is also a batch (see cli/main.py:run is_batch).
    ns = Namespace(format="notion", watch=False, batch=None, workers=4, rsids=["r1", "r2"])
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_positional_batch_notion_workers_gt_1_rejected_in_dispatch(capsys):
    parser = build_parser()
    ns = parser.parse_args(["rsid1", "rsid2", "--format", "notion", "--workers", "4"])
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    err = capsys.readouterr().err.lower()
    assert "workers" in err
    assert "notion" in err


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

    def fake_run(json_path, output_dir=None, force_new=False):
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


def test_watch_notion_rejected_in_dispatch(capsys):
    parser = build_parser()
    ns = parser.parse_args(
        [
            "examplersid1",
            "--watch",
            "--interval",
            "1m",
            "--format",
            "notion",
        ]
    )
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    assert "notion" in capsys.readouterr().err.lower()


def test_batch_notion_workers_gt_1_rejected_in_dispatch(capsys):
    parser = build_parser()
    ns = parser.parse_args(
        [
            "--batch",
            "rsid1",
            "rsid2",
            "--format",
            "notion",
            "--workers",
            "4",
        ]
    )
    rc = _dispatch(ns, parser, [])
    assert rc == int(ExitCode.USAGE)
    err = capsys.readouterr().err.lower()
    assert "workers" in err
    assert "notion" in err


# --- v1.19.0: registry-database flags ---


def test_parser_accepts_notion_registry_database():
    ns = build_parser().parse_args(
        ["examplersid1", "--format", "notion", "--notion-registry-database", "db-id"]
    )
    assert ns.notion_registry_database == "db-id"


def test_parser_accepts_no_notion_registry():
    ns = build_parser().parse_args(
        ["examplersid1", "--format", "notion", "--no-notion-registry"]
    )
    assert ns.no_notion_registry is True


def test_parser_defaults_for_new_flags():
    ns = build_parser().parse_args(["examplersid1"])
    assert ns.notion_registry_database is None
    assert ns.no_notion_registry is False
