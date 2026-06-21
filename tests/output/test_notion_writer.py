"""Tests for NotionWriter, credential resolution, and API layer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.output import registry
from aa_auto_sdr.output.notion_client_guard import resolve_notion_credentials, resolve_notion_token
from aa_auto_sdr.output.notion_registry import REGISTRY_FILENAME
from aa_auto_sdr.output.writers import notion as notion_writer_mod
from aa_auto_sdr.sdr.document import SdrDocument


def _make_doc() -> SdrDocument:
    rs = models.ReportSuite(
        rsid="examplersid1",
        name="Example RS",
        timezone="UTC",
        currency="USD",
        parent_rsid=None,
    )
    return SdrDocument(
        report_suite=rs,
        dimensions=[],
        metrics=[],
        segments=[],
        calculated_metrics=[],
        virtual_report_suites=[],
        classifications=[],
        captured_at=datetime(2026, 5, 14, 10, 0, 0, tzinfo=UTC),
        tool_version="1.18.0",
    )


@pytest.fixture(autouse=True)
def _reset_notion_singleton():
    """Reset the NotionWriter singleton's per-run attrs after each test.

    Tests that set force_new / database_id / disable_registry on the
    registered singleton must not leak that state to later tests (here or in
    other files). pipeline/single.py sets these per-run in production, so a
    clean default after each test matches real behavior.
    """
    yield
    registry.bootstrap()
    nw = registry.get_writer("notion")
    nw.force_new = False
    nw.database_id = None
    nw.disable_registry = False
    nw.company = ""


def test_resolve_notion_credentials_reads_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-page-id")
    assert resolve_notion_credentials() == ("secret-token", "parent-page-id")


def test_resolve_notion_credentials_missing_token_exits(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    with pytest.raises(SystemExit) as exc:
        resolve_notion_credentials()
    assert exc.value.code == 1


def test_resolve_notion_credentials_missing_parent_exits(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    with pytest.raises(SystemExit) as exc:
        resolve_notion_credentials()
    assert exc.value.code == 1


def test_resolve_notion_token_returns_token_without_parent_page(monkeypatch):
    """resolve_notion_token succeeds when only NOTION_TOKEN is set (no NOTION_PARENT_PAGE_ID)."""
    monkeypatch.setenv("NOTION_TOKEN", "token-only")
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    assert resolve_notion_token() == "token-only"


def test_resolve_notion_token_missing_token_exits(monkeypatch):
    """resolve_notion_token exits 1 when NOTION_TOKEN is absent."""
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    with pytest.raises(SystemExit) as exc:
        resolve_notion_token()
    assert exc.value.code == 1


# --- API layer (clear / append / create-or-update) ---


def test_clear_page_blocks_deletes_all_children():
    client = MagicMock()
    client.blocks.children.list.return_value = {
        "results": [{"id": "b1"}, {"id": "b2"}],
        "has_more": False,
    }
    notion_writer_mod._clear_page_blocks(client, "page-id")
    assert client.blocks.delete.call_count == 2


def test_clear_page_blocks_paginates():
    client = MagicMock()
    page1 = {"results": [{"id": "a"}], "has_more": True, "next_cursor": "c1"}
    page2 = {"results": [{"id": "b"}], "has_more": False}
    client.blocks.children.list.side_effect = [page1, page2]
    notion_writer_mod._clear_page_blocks(client, "page-id")
    assert client.blocks.children.list.call_count == 2
    assert client.blocks.delete.call_count == 2


def test_append_blocks_batches_at_100():
    client = MagicMock()
    blocks = [{"type": "paragraph", "paragraph": {}} for _ in range(250)]
    notion_writer_mod._append_blocks(client, "page-id", blocks, batch_size=100)
    assert client.blocks.children.append.call_count == 3


def test_create_or_update_page_creates_new_when_not_in_registry(tmp_path):
    client = MagicMock()
    client.pages.create.return_value = {"id": "new-page-id"}
    registry_path = tmp_path / REGISTRY_FILENAME

    page_id = notion_writer_mod._create_or_update_page(
        client,
        "parent-id",
        "Title",
        "examplersid1",
        [{"type": "paragraph"}],
        registry_path,
        force_new=False,
    )
    assert page_id == "new-page-id"
    client.pages.create.assert_called_once()
    # registry now holds the new id in object shape
    entry = json.loads(registry_path.read_text())["examplersid1"]
    assert entry["current"] == "new-page-id"
    assert entry["superseded"] == []

    # The Notion API expects the title to arrive as a fully-shaped title
    # property object (not a bare rich-text array). Guard the wire shape
    # against accidental regression.
    create_kwargs = client.pages.create.call_args.kwargs
    title_property = create_kwargs["properties"]["title"]
    assert "title" in title_property, "title must be wrapped in a title property object"
    assert title_property["title"][0]["text"]["content"] == "Title"


def test_create_or_update_page_updates_existing_when_in_registry(tmp_path):
    registry_path = tmp_path / REGISTRY_FILENAME
    registry_path.write_text(json.dumps({"examplersid1": "existing-page"}))

    client = MagicMock()
    client.blocks.children.list.return_value = {
        "results": [{"id": "old-block"}],
        "has_more": False,
    }

    page_id = notion_writer_mod._create_or_update_page(
        client,
        "parent-id",
        "Title",
        "examplersid1",
        [{"type": "paragraph"}],
        registry_path,
        force_new=False,
    )
    assert page_id == "existing-page"
    client.pages.create.assert_not_called()
    client.blocks.delete.assert_called_once_with(block_id="old-block")
    client.blocks.children.append.assert_called_once()


def test_create_or_update_page_force_new_ignores_registry(tmp_path):
    registry_path = tmp_path / REGISTRY_FILENAME
    registry_path.write_text(json.dumps({"examplersid1": "existing-page"}))

    client = MagicMock()
    client.pages.create.return_value = {"id": "brand-new-page"}

    page_id = notion_writer_mod._create_or_update_page(
        client,
        "parent-id",
        "Title",
        "examplersid1",
        [{"type": "paragraph"}],
        registry_path,
        force_new=True,
    )
    assert page_id == "brand-new-page"
    client.pages.create.assert_called_once()
    # registry entry replaced; old id tombstoned in superseded
    entry = json.loads(registry_path.read_text())["examplersid1"]
    assert entry["current"] == "brand-new-page"
    assert entry["superseded"] == ["existing-page"]


# --- NotionWriter end-to-end ---


def test_notion_writer_register_in_registry():
    registry.bootstrap()
    writer = registry.get_writer("notion")
    assert writer.__class__.__name__ == "NotionWriter"


def test_notion_writer_write_returns_registry_path(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent")
    doc = _make_doc()
    output_path = tmp_path / f"{doc.report_suite.rsid}.notion"

    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "page-xyz"}

    Client_factory = MagicMock(return_value=mock_client)
    with patch.object(notion_writer_mod, "_require_notion_client", return_value=Client_factory):
        writer = notion_writer_mod.NotionWriter()
        writer.force_new = False
        result = writer.write(doc, output_path)

    assert result == [tmp_path / REGISTRY_FILENAME]
    mock_client.pages.create.assert_called_once()


def test_notion_writer_force_new_creates_fresh_page(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent")
    doc = _make_doc()
    # Pre-existing registry entry
    (tmp_path / REGISTRY_FILENAME).write_text(json.dumps({"examplersid1": "old-page"}))
    output_path = tmp_path / f"{doc.report_suite.rsid}.notion"

    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "fresh-page"}
    Client_factory = MagicMock(return_value=mock_client)

    with patch.object(notion_writer_mod, "_require_notion_client", return_value=Client_factory):
        writer = notion_writer_mod.NotionWriter()
        writer.force_new = True
        writer.write(doc, output_path)

    mock_client.pages.create.assert_called_once()
    # old page id moved to superseded; current points to fresh page
    entry = json.loads((tmp_path / REGISTRY_FILENAME).read_text())["examplersid1"]
    assert entry["current"] == "fresh-page"
    assert entry["superseded"] == ["old-page"]


def test_notion_writer_emits_structured_log(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent")
    doc = _make_doc()
    output_path = tmp_path / f"{doc.report_suite.rsid}.notion"

    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "page-xyz"}
    Client_factory = MagicMock(return_value=mock_client)

    with (
        patch.object(notion_writer_mod, "_require_notion_client", return_value=Client_factory),
        caplog.at_level("INFO", logger=notion_writer_mod.logger.name),
    ):
        writer = notion_writer_mod.NotionWriter()
        writer.write(doc, output_path)

    assert any("format=notion" in r.message for r in caplog.records)


# --- v1.19.0: registry database-ID resolver ---


def test_resolve_notion_database_id_returns_none_when_unset(monkeypatch):
    from aa_auto_sdr.output.notion_client_guard import resolve_notion_database_id

    monkeypatch.delenv("NOTION_REGISTRY_DATABASE_ID", raising=False)
    assert resolve_notion_database_id(cli_override=None, disabled=False) is None


def test_resolve_notion_database_id_uses_env(monkeypatch):
    from aa_auto_sdr.output.notion_client_guard import resolve_notion_database_id

    monkeypatch.setenv("NOTION_REGISTRY_DATABASE_ID", "env-db-id")
    assert resolve_notion_database_id(cli_override=None, disabled=False) == "env-db-id"


def test_resolve_notion_database_id_cli_override_wins(monkeypatch):
    from aa_auto_sdr.output.notion_client_guard import resolve_notion_database_id

    monkeypatch.setenv("NOTION_REGISTRY_DATABASE_ID", "env-db-id")
    assert resolve_notion_database_id(cli_override="flag-db-id", disabled=False) == "flag-db-id"


def test_resolve_notion_database_id_disabled_short_circuits(monkeypatch):
    from aa_auto_sdr.output.notion_client_guard import resolve_notion_database_id

    monkeypatch.setenv("NOTION_REGISTRY_DATABASE_ID", "env-db-id")
    assert resolve_notion_database_id(cli_override="flag-db-id", disabled=True) is None


def test_notion_writer_has_database_id_and_disable_registry_attrs():
    """NotionWriter exposes the per-run knobs pipeline/single.py mutates.

    Mirrors the v1.18.0 force_new pattern: pipeline reaches the registered
    singleton via `registry.get_writer("notion")` and sets the attributes
    before `write()` runs.
    """
    from aa_auto_sdr.output import registry as out_registry

    out_registry.bootstrap()
    nw = out_registry.get_writer("notion")

    assert nw.database_id is None
    assert nw.disable_registry is False

    nw.database_id = "db-from-pipeline"
    nw.disable_registry = True

    assert out_registry.get_writer("notion") is nw  # singleton identity
    assert nw.database_id == "db-from-pipeline"
    assert nw.disable_registry is True

    # Restore for downstream tests
    nw.database_id = None
    nw.disable_registry = False


# --- v1.19.0: writer wires the database upsert ---


def test_writer_skips_database_when_id_is_none(monkeypatch, tmp_path):
    """Behavior is byte-identical to v1.18.0 when database_id is None."""
    registry.bootstrap()
    writer = registry.get_writer("notion")
    writer.database_id = None
    writer.disable_registry = False
    writer.force_new = False

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent")
    monkeypatch.delenv("NOTION_REGISTRY_DATABASE_ID", raising=False)

    fake_client = MagicMock()
    fake_client.pages.create.return_value = {"id": "page-1"}
    fake_client.blocks.children.list.return_value = {"results": [], "has_more": False}

    monkeypatch.setattr(
        notion_writer_mod,
        "_require_notion_client",
        lambda: MagicMock(return_value=fake_client),
    )

    paths = writer.write(_make_doc(), tmp_path / "examplersid1.notion")

    assert paths == [tmp_path / REGISTRY_FILENAME]
    fake_client.databases.retrieve.assert_not_called()
    fake_client.data_sources.query.assert_not_called()


def test_writer_upserts_row_when_database_id_set(monkeypatch, tmp_path):
    registry.bootstrap()
    writer = registry.get_writer("notion")
    writer.database_id = "db-id"
    writer.disable_registry = False
    writer.force_new = False

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent")

    fake_client = MagicMock()
    fake_client.blocks.children.list.return_value = {"results": [], "has_more": False}
    fake_client.databases.retrieve.return_value = {"data_sources": [{"id": "ds-1", "name": "ds"}]}
    fake_client.data_sources.retrieve.return_value = {
        "properties": {
            p: {"type": "x"}
            for p in (
                "Name",
                "RSID",
                "Last Updated",
                "Tool Version",
                "Dimensions",
                "Metrics",
                "Segments",
                "Calculated Metrics",
                "Virtual Report Suites",
                "Classifications",
            )
        },
    }
    fake_client.data_sources.query.return_value = {"results": []}
    fake_client.pages.create.side_effect = [
        {"id": "page-1"},  # detail page
        {"id": "row-1"},  # database row
    ]

    monkeypatch.setattr(
        notion_writer_mod,
        "_require_notion_client",
        lambda: MagicMock(return_value=fake_client),
    )

    writer.write(_make_doc(), tmp_path / "examplersid1.notion")

    fake_client.databases.retrieve.assert_called_once_with(database_id="db-id")
    fake_client.data_sources.query.assert_called_once()


def test_writer_logs_registry_skipped_when_no_db(monkeypatch, tmp_path, caplog):
    """notion_registry_skipped is emitted at DEBUG when database_id resolves to None."""
    import logging

    registry.bootstrap()
    writer = registry.get_writer("notion")
    writer.database_id = None
    writer.disable_registry = False
    writer.force_new = False

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent")
    monkeypatch.delenv("NOTION_REGISTRY_DATABASE_ID", raising=False)

    fake_client = MagicMock()
    fake_client.pages.create.return_value = {"id": "page-1"}
    fake_client.blocks.children.list.return_value = {"results": [], "has_more": False}

    monkeypatch.setattr(
        notion_writer_mod,
        "_require_notion_client",
        lambda: MagicMock(return_value=fake_client),
    )

    with caplog.at_level(logging.DEBUG, logger="aa_auto_sdr.output.writers.notion"):
        writer.write(_make_doc(), tmp_path / "examplersid1.notion")

    assert any("notion_registry_skipped" in r.message for r in caplog.records)


def test_writer_continues_when_database_upsert_fails(monkeypatch, tmp_path, caplog):
    """Detail page is the primary artifact — DB errors WARN and continue."""
    import logging

    registry.bootstrap()
    writer = registry.get_writer("notion")
    writer.database_id = "db-id"
    writer.disable_registry = False
    writer.force_new = False

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent")

    fake_client = MagicMock()
    fake_client.pages.create.return_value = {"id": "page-1"}
    fake_client.blocks.children.list.return_value = {"results": [], "has_more": False}
    fake_client.databases.retrieve.side_effect = Exception("simulated 401")

    monkeypatch.setattr(
        notion_writer_mod,
        "_require_notion_client",
        lambda: MagicMock(return_value=fake_client),
    )

    with caplog.at_level(logging.WARNING, logger="aa_auto_sdr.output.writers.notion"):
        paths = writer.write(_make_doc(), tmp_path / "examplersid1.notion")

    assert paths == [tmp_path / REGISTRY_FILENAME]
    assert any("notion_registry_unavailable" in r.message for r in caplog.records)


# --- v1.20.0: company threading through the writer ---


def test_writer_threads_company_to_upsert(monkeypatch, tmp_path):
    """writer.company is forwarded as company= kwarg to upsert_row."""
    captured: dict = {}

    def fake_upsert(client, **kwargs):
        captured.update(kwargs)
        return "row1"

    monkeypatch.setattr("aa_auto_sdr.output.writers.notion.upsert_row", fake_upsert)
    monkeypatch.setattr(
        "aa_auto_sdr.output.writers.notion.resolve_notion_database_id",
        lambda **_kwargs: "db1",
    )
    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent")

    fake_client = MagicMock()
    fake_client.pages.create.return_value = {"id": "page-1"}
    fake_client.blocks.children.list.return_value = {"results": [], "has_more": False}

    monkeypatch.setattr(
        notion_writer_mod,
        "_require_notion_client",
        lambda: MagicMock(return_value=fake_client),
    )

    registry.bootstrap()
    writer = registry.get_writer("notion")
    writer.database_id = "db1"
    writer.disable_registry = False
    writer.force_new = False
    writer.company = "acme"

    writer.write(_make_doc(), tmp_path / "examplersid1.notion")

    assert captured.get("company") == "acme"


def test_writer_company_attr_defaults_to_empty_string():
    """NotionWriter exposes company as a class attribute defaulting to empty string."""
    from aa_auto_sdr.output import registry as out_registry

    out_registry.bootstrap()
    nw = out_registry.get_writer("notion")
    assert nw.company == ""
