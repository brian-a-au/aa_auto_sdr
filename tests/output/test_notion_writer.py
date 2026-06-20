"""Tests for NotionWriter, credential resolution, and API layer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.api import models
from aa_auto_sdr.output import registry
from aa_auto_sdr.output.notion_client_guard import resolve_notion_credentials
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
    # registry now holds the new id
    assert json.loads(registry_path.read_text())["examplersid1"] == "new-page-id"

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
    # registry entry replaced
    assert json.loads(registry_path.read_text())["examplersid1"] == "brand-new-page"


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
    assert json.loads((tmp_path / REGISTRY_FILENAME).read_text())["examplersid1"] == "fresh-page"


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
