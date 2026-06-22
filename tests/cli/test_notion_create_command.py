"""Tests for the --notion-create-database command handler."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from tests._notion_fakes import FakeCreateClient


def _patch_guard(mod, client=None):
    """Patch credential + client resolution on the handler module."""
    factory = MagicMock(return_value=client) if client is not None else MagicMock()
    return (
        patch.object(mod, "resolve_notion_credentials", return_value=("tok", "pp-1")),
        patch.object(mod, "_require_notion_client", return_value=factory),
        factory,
    )


def test_dry_run_makes_no_calls(capsys):
    from aa_auto_sdr.cli.commands import notion_create as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    p_creds, p_client, factory = _patch_guard(mod)
    with p_creds, p_client:
        code = mod.run_notion_create_database(title="AA SDR Registry", dry_run=True, registry_already_configured=False)

    assert code == int(ExitCode.OK)
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "pp-1" in out  # target parent shown
    factory.assert_not_called()  # no client constructed in dry-run


def test_dry_run_emits_planned_log(caplog):
    from aa_auto_sdr.cli.commands import notion_create as mod

    p_creds, p_client, _ = _patch_guard(mod)
    with p_creds, p_client, caplog.at_level(logging.INFO, logger="aa_auto_sdr.cli.commands.notion_create"):
        mod.run_notion_create_database(title="AA SDR Registry", dry_run=True, registry_already_configured=False)

    assert any("notion_create_planned" in r.message for r in caplog.records)


def test_apply_creates_and_prints_id(capsys):
    from aa_auto_sdr.cli.commands import notion_create as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    client = FakeCreateClient(database_id="db-xyz")
    p_creds, p_client, _ = _patch_guard(mod, client)
    with p_creds, p_client:
        code = mod.run_notion_create_database(title="AA SDR Registry", dry_run=False, registry_already_configured=False)

    assert code == int(ExitCode.OK)
    assert len(client.create_calls) == 1
    out = capsys.readouterr().out
    assert "db-xyz" in out
    assert "NOTION_REGISTRY_DATABASE_ID" in out


def test_apply_emits_created_log(caplog):
    from aa_auto_sdr.cli.commands import notion_create as mod

    client = FakeCreateClient(database_id="db-xyz")
    p_creds, p_client, _ = _patch_guard(mod, client)
    with p_creds, p_client, caplog.at_level(logging.INFO, logger="aa_auto_sdr.cli.commands.notion_create"):
        mod.run_notion_create_database(title="AA SDR Registry", dry_run=False, registry_already_configured=False)

    assert any("notion_database_created" in r.message for r in caplog.records)


def test_apply_title_override_reaches_create(capsys):
    from aa_auto_sdr.cli.commands import notion_create as mod

    client = FakeCreateClient()
    p_creds, p_client, _ = _patch_guard(mod, client)
    with p_creds, p_client:
        mod.run_notion_create_database(title="Prod Registry", dry_run=False, registry_already_configured=False)

    assert client.create_calls[0]["title"][0]["text"]["content"] == "Prod Registry"


def test_warn_when_registry_already_configured(caplog):
    from aa_auto_sdr.cli.commands import notion_create as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    p_creds, p_client, _ = _patch_guard(mod)
    with p_creds, p_client, caplog.at_level(logging.WARNING, logger="aa_auto_sdr.cli.commands.notion_create"):
        code = mod.run_notion_create_database(title="AA SDR Registry", dry_run=True, registry_already_configured=True)

    assert code == int(ExitCode.OK)
    assert any("notion_create_existing_registry" in r.message for r in caplog.records)


def test_sdk_error_returns_generic(caplog):
    from aa_auto_sdr.cli.commands import notion_create as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    client = FakeCreateClient(raises=RuntimeError("boom"))
    p_creds, p_client, _ = _patch_guard(mod, client)
    with p_creds, p_client, caplog.at_level(logging.WARNING, logger="aa_auto_sdr.cli.commands.notion_create"):
        code = mod.run_notion_create_database(title="AA SDR Registry", dry_run=False, registry_already_configured=False)

    assert code == int(ExitCode.GENERIC)
    assert any("notion_create_failed" in r.message for r in caplog.records)


def test_missing_credentials_exits_via_guard():
    import pytest

    from aa_auto_sdr.cli.commands import notion_create as mod

    with patch.object(mod, "resolve_notion_credentials", side_effect=SystemExit(1)), pytest.raises(SystemExit):
        mod.run_notion_create_database(title="AA SDR Registry", dry_run=True, registry_already_configured=False)


def _ns(**kw):
    import argparse

    return argparse.Namespace(**kw)


def test_validate_title_requires_create_mode():
    from aa_auto_sdr.cli.main import _validate_notion_modifiers
    from aa_auto_sdr.core.exit_codes import ExitCode

    ns = _ns(notion_create_database=False, notion_database_title="X")
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_validate_create_rejects_positional_rsid():
    from aa_auto_sdr.cli.main import _validate_notion_modifiers
    from aa_auto_sdr.core.exit_codes import ExitCode

    ns = _ns(notion_create_database=True, rsids=["myrs"])
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_validate_create_rejects_combined_repair():
    from aa_auto_sdr.cli.main import _validate_notion_modifiers
    from aa_auto_sdr.core.exit_codes import ExitCode

    ns = _ns(notion_create_database=True, notion_repair_database=True, notion_registry_database="db")
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_validate_create_with_yes_is_allowed():
    from aa_auto_sdr.cli.main import _validate_notion_modifiers
    from aa_auto_sdr.core.exit_codes import ExitCode

    ns = _ns(notion_create_database=True, yes=True)
    assert _validate_notion_modifiers(ns) == int(ExitCode.OK)


def test_validate_create_alone_is_allowed():
    from aa_auto_sdr.cli.main import _validate_notion_modifiers
    from aa_auto_sdr.core.exit_codes import ExitCode

    ns = _ns(notion_create_database=True)
    assert _validate_notion_modifiers(ns) == int(ExitCode.OK)


def test_validate_create_rejects_list_metrics():
    from aa_auto_sdr.cli.main import _validate_notion_modifiers
    from aa_auto_sdr.core.exit_codes import ExitCode

    ns = _ns(notion_create_database=True, list_metrics="RS1")
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_validate_create_rejects_inventory_summary():
    from aa_auto_sdr.cli.main import _validate_notion_modifiers
    from aa_auto_sdr.core.exit_codes import ExitCode

    ns = _ns(notion_create_database=True, inventory_summary=True)
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_validate_create_rejects_config_status():
    from aa_auto_sdr.cli.main import _validate_notion_modifiers
    from aa_auto_sdr.core.exit_codes import ExitCode

    ns = _ns(notion_create_database=True, config_status=True)
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_validate_create_rejects_profile_list():
    from aa_auto_sdr.cli.main import _validate_notion_modifiers
    from aa_auto_sdr.core.exit_codes import ExitCode

    ns = _ns(notion_create_database=True, profile_list=True)
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_validate_create_rejects_interactive():
    from aa_auto_sdr.cli.main import _validate_notion_modifiers
    from aa_auto_sdr.core.exit_codes import ExitCode

    ns = _ns(notion_create_database=True, interactive=True)
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_validate_create_rejects_snapshot_lifecycle():
    from aa_auto_sdr.cli.main import _validate_notion_modifiers
    from aa_auto_sdr.core.exit_codes import ExitCode

    ns = _ns(notion_create_database=True, prune_snapshots=True)
    assert _validate_notion_modifiers(ns) == int(ExitCode.USAGE)


def test_apply_warn_but_proceed_when_registry_already_configured(caplog):
    """Apply path (dry_run=False) with an existing registry: warns but still creates."""
    from aa_auto_sdr.cli.commands import notion_create as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    client = FakeCreateClient(database_id="db-new")
    p_creds, p_client, _ = _patch_guard(mod, client)
    with p_creds, p_client, caplog.at_level(logging.WARNING, logger="aa_auto_sdr.cli.commands.notion_create"):
        code = mod.run_notion_create_database(title="AA SDR Registry", dry_run=False, registry_already_configured=True)

    assert any("notion_create_existing_registry" in r.message for r in caplog.records)
    assert len(client.create_calls) == 1
    assert code == int(ExitCode.OK)
