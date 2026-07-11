"""Coverage for dispatch + validation branches in cli/main.py.

Most tests drive ``_dispatch`` directly with a fully-parsed namespace (mirroring
what ``run()`` builds, minus logging side effects) and monkeypatch the command
handlers. Validator helpers are exercised via direct calls with constructed
namespaces, matching the style in tests/cli/test_cli_notion.py and
tests/cli/test_notion_create_command.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from aa_auto_sdr.cli.main import (
    _derive_quiet_from_output_destination,
    _dispatch,
    _resolve_retry_policy,
    _validate_template_modifiers,
)
from aa_auto_sdr.cli.parser import build_parser
from aa_auto_sdr.core.exit_codes import ExitCode


def _dispatch_argv(argv: list[str]) -> int:
    """Parse argv into a namespace and run _dispatch, mirroring run()'s prelude
    of attaching a resolved retry policy. No logging is configured."""
    parser = build_parser()
    ns = parser.parse_args(argv)
    ns.retry_policy = _resolve_retry_policy(ns)
    return _dispatch(ns, parser, argv)


# --- _derive_quiet_from_output_destination (line 52) -----------------------


def test_derive_quiet_returns_early_when_already_quiet() -> None:
    ns = argparse.Namespace(quiet=True, output="-", run_summary_json=None)
    _derive_quiet_from_output_destination(ns)
    assert ns.quiet is True  # untouched — early return


# --- _validate_template_modifiers (lines 172-228) --------------------------


def test_template_organization_requires_template() -> None:
    ns = argparse.Namespace(template=None, template_organization="Acme")
    assert _validate_template_modifiers(ns) == int(ExitCode.USAGE)


def test_template_not_found(tmp_path: Path) -> None:
    ns = build_parser().parse_args(["rs1", "--template", str(tmp_path / "missing.xlsx")])
    assert _validate_template_modifiers(ns) == int(ExitCode.USAGE)


def test_template_path_is_not_a_file(tmp_path: Path) -> None:
    # A directory exists() but is not is_file().
    ns = build_parser().parse_args(["rs1", "--template", str(tmp_path)])
    assert _validate_template_modifiers(ns) == int(ExitCode.USAGE)


def test_template_must_be_xlsx(tmp_path: Path) -> None:
    txt = tmp_path / "template.txt"
    txt.write_text("")
    ns = build_parser().parse_args(["rs1", "--template", str(txt)])
    assert _validate_template_modifiers(ns) == int(ExitCode.USAGE)


def test_template_rejects_non_generating_action(tmp_path: Path) -> None:
    xlsx = tmp_path / "template.xlsx"
    xlsx.write_text("")
    ns = build_parser().parse_args(["rs1", "--template", str(xlsx), "--stats"])
    assert _validate_template_modifiers(ns) == int(ExitCode.USAGE)


def test_template_requires_excel_format(tmp_path: Path) -> None:
    xlsx = tmp_path / "template.xlsx"
    xlsx.write_text("")
    ns = build_parser().parse_args(["rs1", "--template", str(xlsx), "--format", "json"])
    assert _validate_template_modifiers(ns) == int(ExitCode.USAGE)


def test_template_unknown_format_defers_to_generate(tmp_path: Path) -> None:
    """An unknown --format makes resolve_formats raise KeyError; the validator
    defers (returns OK) so the generate path surfaces its own error."""
    xlsx = tmp_path / "template.xlsx"
    xlsx.write_text("")
    ns = build_parser().parse_args(["rs1", "--template", str(xlsx), "--format", "totally-bogus"])
    assert _validate_template_modifiers(ns) == int(ExitCode.OK)


def test_template_excel_format_passes(tmp_path: Path) -> None:
    xlsx = tmp_path / "template.xlsx"
    xlsx.write_text("")
    ns = build_parser().parse_args(["rs1", "--template", str(xlsx)])
    assert _validate_template_modifiers(ns) == int(ExitCode.OK)


# --- validator-failure short-circuits inside _dispatch (572 / 576 / 580) ----


def test_dispatch_returns_watch_modifier_usage() -> None:
    # --interval without --watch fails _validate_watch_modifiers.
    assert _dispatch_argv(["rs1", "--interval", "1h"]) == int(ExitCode.USAGE)


def test_dispatch_returns_git_modifier_usage() -> None:
    # --git-push without --git-commit fails _validate_git_modifiers.
    assert _dispatch_argv(["rs1", "--git-push"]) == int(ExitCode.USAGE)


def test_dispatch_returns_template_modifier_usage(tmp_path: Path) -> None:
    # Missing template file fails _validate_template_modifiers in dispatch.
    assert _dispatch_argv(["rs1", "--template", str(tmp_path / "nope.xlsx")]) == int(ExitCode.USAGE)


# --- push-to-notion output-dir scan end-of-options break (line 607) ---------


def test_push_to_notion_stops_output_dir_scan_at_double_dash(monkeypatch: pytest.MonkeyPatch) -> None:
    import aa_auto_sdr.cli.commands.push_to_notion as push_mod

    captured: dict[str, object] = {}

    def _stub(input_file: object, **kwargs: object) -> int:
        captured["input_file"] = input_file
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(push_mod, "run_push_to_notion", _stub)
    rc = _dispatch_argv(["--push-to-notion", "sdr.json", "--"])
    assert rc == 0
    assert captured["input_file"] == "sdr.json"
    # The "--" terminator means no explicit --output-dir was detected.
    assert captured["output_dir"] is None


# --- standalone notion maintenance modes (624-626 / 629-633 / 636-643) ------


def test_dispatch_notion_prune_orphans(monkeypatch: pytest.MonkeyPatch) -> None:
    import aa_auto_sdr.cli.commands.notion_prune as prune_mod

    captured: dict[str, object] = {}

    def _stub(output_dir: object, *, dry_run: bool) -> int:
        captured["output_dir"] = output_dir
        captured["dry_run"] = dry_run
        return 0

    monkeypatch.setattr(prune_mod, "run_notion_prune_orphans", _stub)
    rc = _dispatch_argv(["--notion-prune-orphans"])
    assert rc == 0
    assert captured["dry_run"] is True  # no --yes → dry-run


def test_dispatch_notion_repair_database(monkeypatch: pytest.MonkeyPatch) -> None:
    import aa_auto_sdr.cli.commands.notion_repair as repair_mod

    captured: dict[str, object] = {}

    def _stub(db_id: object, *, dry_run: bool) -> int:
        captured["db_id"] = db_id
        captured["dry_run"] = dry_run
        return 0

    monkeypatch.setattr(repair_mod, "run_notion_repair_database", _stub)
    rc = _dispatch_argv(["--notion-repair-database", "--notion-registry-database", "db-123"])
    assert rc == 0
    assert captured["db_id"] == "db-123"


def test_dispatch_notion_create_database(monkeypatch: pytest.MonkeyPatch) -> None:
    import aa_auto_sdr.cli.commands.notion_create as create_mod

    monkeypatch.delenv("NOTION_REGISTRY_DATABASE_ID", raising=False)
    captured: dict[str, object] = {}

    def _stub(*, title: str, dry_run: bool, registry_already_configured: bool) -> int:
        captured["title"] = title
        captured["dry_run"] = dry_run
        captured["registry_already_configured"] = registry_already_configured
        return 0

    monkeypatch.setattr(create_mod, "run_notion_create_database", _stub)
    rc = _dispatch_argv(["--notion-create-database"])
    assert rc == 0
    assert captured["dry_run"] is True
    assert captured["title"] == create_mod.DEFAULT_REGISTRY_TITLE


# --- profile-import + extra positionals (678-682) ---------------------------


def test_profile_import_rejects_extra_positionals(capsys: pytest.CaptureFixture[str]) -> None:
    rc = _dispatch_argv(["--profile-import", "prod", "/tmp/c.json", "extra-rsid"])
    assert rc == int(ExitCode.USAGE)
    assert "--profile-import takes" in capsys.readouterr().err


# --- quality-policy loading (687-697) ---------------------------------------


def test_quality_policy_load_failure_returns_config_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text('{"bogus_key": 1}')  # unknown key → ConfigError
    rc = _dispatch_argv(["rs1", "--quality-policy", str(policy)])
    assert rc == int(ExitCode.CONFIG)
    assert "error:" in capsys.readouterr().err


def test_quality_policy_loaded_then_generates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import aa_auto_sdr.cli.commands.generate as generate_mod

    captured: dict[str, object] = {}

    def _stub(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(generate_mod, "run", _stub)
    policy = tmp_path / "policy.json"
    policy.write_text('{"fail_on_quality": "HIGH", "quality_report": "json"}')
    rc = _dispatch_argv(["rs1", "--quality-policy", str(policy)])
    assert rc == 0
    # Policy filled the unset CLI fields before generate dispatch.
    assert captured["fail_on_quality"] == "HIGH"
    assert captured["quality_report"] == "json"


# --- quality flags rejected with non-SDR actions (729-734) ------------------


def test_quality_flags_rejected_with_non_sdr_action(capsys: pytest.CaptureFixture[str]) -> None:
    rc = _dispatch_argv(["--stats", "rs1", "--fail-on-quality", "HIGH"])
    assert rc == int(ExitCode.USAGE)
    assert "require" in capsys.readouterr().err.lower()


# --- profile / config dispatch (740 / 748 / 892-894 / 896-898) --------------


def test_dispatch_profile_add(monkeypatch: pytest.MonkeyPatch) -> None:
    import aa_auto_sdr.cli.commands.config as config_mod

    captured: dict[str, object] = {}

    def _stub(name: object) -> int:
        captured["name"] = name
        return 0

    monkeypatch.setattr(config_mod, "profile_add", _stub)
    rc = _dispatch_argv(["--profile-add", "myprofile"])
    assert rc == 0
    assert captured["name"] == "myprofile"


def test_dispatch_validate_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import aa_auto_sdr.cli.commands.config as config_mod

    captured: dict[str, object] = {}

    def _stub(*, profile: object) -> int:
        captured["profile"] = profile
        return 0

    monkeypatch.setattr(config_mod, "validate_config", _stub)
    rc = _dispatch_argv(["--validate-config"])
    assert rc == 0
    assert "profile" in captured


def test_dispatch_profile_test(monkeypatch: pytest.MonkeyPatch) -> None:
    import aa_auto_sdr.cli.commands.profiles as prof_mod

    captured: dict[str, object] = {}

    def _stub(name: object, *, retry_policy: object) -> int:
        captured["name"] = name
        return 0

    monkeypatch.setattr(prof_mod, "test_run", _stub)
    rc = _dispatch_argv(["--profile-test", "prod"])
    assert rc == 0
    assert captured["name"] == "prod"


def test_dispatch_profile_show(monkeypatch: pytest.MonkeyPatch) -> None:
    import aa_auto_sdr.cli.commands.profiles as prof_mod

    captured: dict[str, object] = {}

    def _stub(name: object) -> int:
        captured["name"] = name
        return 0

    monkeypatch.setattr(prof_mod, "show_run", _stub)
    rc = _dispatch_argv(["--profile-show", "prod"])
    assert rc == 0
    assert captured["name"] == "prod"


# --- prune-snapshots with >1 positional (866-870) ---------------------------


def test_prune_snapshots_rejects_multiple_positionals(capsys: pytest.CaptureFixture[str]) -> None:
    rc = _dispatch_argv(["--prune-snapshots", "rs1", "rs2"])
    assert rc == int(ExitCode.USAGE)
    assert "at most one positional" in capsys.readouterr().err


# --- list-virtual-reportsuites dispatch (940-948) ---------------------------


def test_dispatch_list_virtual_reportsuites(monkeypatch: pytest.MonkeyPatch) -> None:
    import aa_auto_sdr.cli.commands.discovery as discovery_mod

    captured: dict[str, object] = {}

    def _stub(**kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(discovery_mod, "run_list_virtual_reportsuites", _stub)
    rc = _dispatch_argv(["--list-virtual-reportsuites", "--profile", "prod"])
    assert rc == 0
    assert captured["profile"] == "prod"
