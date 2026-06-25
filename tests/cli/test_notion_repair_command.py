"""Tests for the --notion-repair-database command handler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests._notion_fakes import FakeRepairClient as _FakeRepairClient


def test_dry_run_prints_and_no_update(capsys):
    """dry_run=True → output contains 'DRY RUN', no update call, returns ExitCode.OK."""
    from aa_auto_sdr.cli.commands import notion_repair as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    client = _FakeRepairClient(missing_prop="Company")
    Client_factory = MagicMock(return_value=client)

    with (
        patch.object(mod, "_require_notion_client", return_value=Client_factory),
        patch.object(mod, "resolve_notion_token", return_value="tok"),
    ):
        code = mod.run_notion_repair_database(database_id="db-id", dry_run=True)

    assert code == int(ExitCode.OK)
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert client.update_calls == []


def test_apply_calls_update_and_returns_ok(capsys):
    """dry_run=False, missing property → data_sources.update called, returns ExitCode.OK."""
    from aa_auto_sdr.cli.commands import notion_repair as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    client = _FakeRepairClient(missing_prop="Timezone")
    Client_factory = MagicMock(return_value=client)

    with (
        patch.object(mod, "_require_notion_client", return_value=Client_factory),
        patch.object(mod, "resolve_notion_token", return_value="tok"),
    ):
        code = mod.run_notion_repair_database(database_id="db-id", dry_run=False)

    assert code == int(ExitCode.OK)
    assert len(client.update_calls) == 1


def test_dry_run_emits_structured_log(caplog):
    """dry_run=True emits notion_repair_planned with correct add/conflicts counts."""
    import logging

    from aa_auto_sdr.cli.commands import notion_repair as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    client = _FakeRepairClient(missing_prop="Company")
    Client_factory = MagicMock(return_value=client)

    with (
        patch.object(mod, "_require_notion_client", return_value=Client_factory),
        patch.object(mod, "resolve_notion_token", return_value="tok"),
        caplog.at_level(logging.INFO, logger="aa_auto_sdr.cli.commands.notion_repair"),
    ):
        code = mod.run_notion_repair_database(database_id="db-id", dry_run=True)

    assert code == int(ExitCode.OK)
    assert any(
        "notion_repair_planned" in r.message and "add=" in r.message and "conflicts=" in r.message
        for r in caplog.records
    )


def test_live_run_does_not_emit_repair_planned_log(caplog):
    """dry_run=False must NOT emit notion_repair_planned."""
    import logging

    from aa_auto_sdr.cli.commands import notion_repair as mod

    client = _FakeRepairClient(missing_prop="Company")
    Client_factory = MagicMock(return_value=client)

    with (
        patch.object(mod, "_require_notion_client", return_value=Client_factory),
        patch.object(mod, "resolve_notion_token", return_value="tok"),
        caplog.at_level(logging.INFO, logger="aa_auto_sdr.cli.commands.notion_repair"),
    ):
        mod.run_notion_repair_database(database_id="db-id", dry_run=False)

    assert not any("notion_repair_planned" in r.message for r in caplog.records)


def _conflict_client():
    """A FakeRepairClient whose first canonical property has the wrong type
    (forces a single ``conflicts`` entry, no ``to_add``)."""
    from aa_auto_sdr.output.notion_database import PROPERTY_SCHEMA

    existing = {name: {"type": schema["type"]} for name, schema in PROPERTY_SCHEMA.items()}
    first = next(iter(existing))
    existing[first] = {"type": "checkbox" if existing[first]["type"] != "checkbox" else "rich_text"}
    return _FakeRepairClient(existing_props=existing)


def test_notion_registry_error_returns_generic(capsys):
    """A NotionRegistryError from repair_database → printed error, ExitCode.GENERIC."""
    from aa_auto_sdr.cli.commands import notion_repair as mod
    from aa_auto_sdr.core.exit_codes import ExitCode
    from aa_auto_sdr.output.notion_database import NotionRegistryError

    Client_factory = MagicMock(return_value=MagicMock())
    with (
        patch.object(mod, "_require_notion_client", return_value=Client_factory),
        patch.object(mod, "resolve_notion_token", return_value="tok"),
        patch.object(mod, "repair_database", side_effect=NotionRegistryError("no data source")),
    ):
        code = mod.run_notion_repair_database(database_id="db-id", dry_run=True)

    assert code == int(ExitCode.GENERIC)
    assert "--notion-repair-database" in capsys.readouterr().out


def test_unexpected_exception_returns_generic(capsys):
    """A generic Exception from repair_database → stderr error, ExitCode.GENERIC."""
    from aa_auto_sdr.cli.commands import notion_repair as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    Client_factory = MagicMock(return_value=MagicMock())
    with (
        patch.object(mod, "_require_notion_client", return_value=Client_factory),
        patch.object(mod, "resolve_notion_token", return_value="tok"),
        patch.object(mod, "repair_database", side_effect=RuntimeError("boom")),
    ):
        code = mod.run_notion_repair_database(database_id="db-id", dry_run=True)

    assert code == int(ExitCode.GENERIC)
    assert "RuntimeError" in capsys.readouterr().err


def test_dry_run_reports_type_conflicts(capsys):
    """dry_run=True with a type conflict prints a '!' conflict line."""
    from aa_auto_sdr.cli.commands import notion_repair as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    client = _conflict_client()
    Client_factory = MagicMock(return_value=client)
    with (
        patch.object(mod, "_require_notion_client", return_value=Client_factory),
        patch.object(mod, "resolve_notion_token", return_value="tok"),
    ):
        code = mod.run_notion_repair_database(database_id="db-id", dry_run=True)

    assert code == int(ExitCode.OK)
    out = capsys.readouterr().out
    assert "! " in out
    assert "want" in out
    # A pure conflict (no missing props) sends no update.
    assert client.update_calls == []


def test_apply_logs_type_conflicts(caplog):
    """dry_run=False with a type conflict emits notion_repair_type_conflict (WARNING)."""
    import logging

    from aa_auto_sdr.cli.commands import notion_repair as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    client = _conflict_client()
    Client_factory = MagicMock(return_value=client)
    with (
        patch.object(mod, "_require_notion_client", return_value=Client_factory),
        patch.object(mod, "resolve_notion_token", return_value="tok"),
        caplog.at_level(logging.WARNING, logger="aa_auto_sdr.cli.commands.notion_repair"),
    ):
        code = mod.run_notion_repair_database(database_id="db-id", dry_run=False)

    assert code == int(ExitCode.OK)
    assert any("notion_repair_type_conflict" in r.message for r in caplog.records)
