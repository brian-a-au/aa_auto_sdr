"""Tests for the --notion-repair-database command handler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class _FakeRepairClient:
    """Minimal fake Notion client for repair command tests."""

    def __init__(self, *, missing_prop: str | None = None):
        self.update_calls: list[dict] = []
        self._missing_prop = missing_prop

        from aa_auto_sdr.output.notion_database import PROPERTY_SCHEMA

        existing = {name: {"type": schema["type"]} for name, schema in PROPERTY_SCHEMA.items()}
        if missing_prop:
            del existing[missing_prop]
        self._existing_props = existing

        outer = self

        class _DS:
            def retrieve(self, **kw):
                return {"properties": outer._existing_props}

            def update(self, data_source_id=None, **kw):
                outer.update_calls.append({"data_source_id": data_source_id, **kw})

        class _DBs:
            def retrieve(self, **kw):
                return {"data_sources": [{"id": "ds-repair"}]}

        self.data_sources = _DS()
        self.databases = _DBs()


def test_dry_run_prints_and_no_update(capsys):
    """dry_run=True → output contains 'DRY RUN', no update call, returns ExitCode.OK."""
    from aa_auto_sdr.cli.commands import notion_repair as mod
    from aa_auto_sdr.core.exit_codes import ExitCode

    client = _FakeRepairClient(missing_prop="Company")
    Client_factory = MagicMock(return_value=client)

    with (
        patch.object(mod, "_require_notion_client", return_value=Client_factory),
        patch.object(mod, "resolve_notion_credentials", return_value=("tok", "parent-id")),
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
        patch.object(mod, "resolve_notion_credentials", return_value=("tok", "parent-id")),
    ):
        code = mod.run_notion_repair_database(database_id="db-id", dry_run=False)

    assert code == int(ExitCode.OK)
    assert len(client.update_calls) == 1
