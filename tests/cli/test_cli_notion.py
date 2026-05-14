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
