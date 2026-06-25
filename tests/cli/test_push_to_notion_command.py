"""Tests for the --push-to-notion command path."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_sdr_json(tmp_path: Path) -> Path:
    payload = {
        "report_suite": {
            "rsid": "examplersid1",
            "name": "Example RS",
            "currency": "USD",
            "timezone": "America/Los_Angeles",
            "parent_rsid": None,
        },
        "captured_at": "2026-05-14T10:00:00+00:00",
        "tool_version": "1.18.0",
        "dimensions": [{"id": "evar1", "name": "First eVar"}],
        "metrics": [{"id": "event1", "name": "Custom Event 1"}],
        "segments": [],
        "calculated_metrics": [],
        "virtual_report_suites": [],
        "classifications": [],
        "fetch_status": {},
        "quality": None,
    }
    p = tmp_path / "examplersid1.json"
    p.write_text(json.dumps(payload))
    return p


def _make_snapshot_envelope(tmp_path: Path) -> Path:
    payload = {
        "schema": "aa-sdr-snapshot/v4",
        "rsid": "examplersid1",
        "captured_at": "2026-05-14T10:00:00+00:00",
        "tool_version": "1.18.0",
        "degraded_components": [],
        "partial_components": {},
        "quality": None,
        "components": {
            "report_suite": {
                "rsid": "examplersid1",
                "name": "Example RS",
                "currency": "USD",
                "timezone": "America/Los_Angeles",
                "parent_rsid": None,
            },
            "dimensions": [{"id": "evar1", "name": "First eVar"}],
            "metrics": [{"id": "event1", "name": "Custom Event 1"}],
            "segments": [],
            "calculated_metrics": [],
            "virtual_report_suites": [],
            "classifications": [],
        },
    }
    p = tmp_path / "snapshot.json"
    p.write_text(json.dumps(payload))
    return p


def test_push_to_notion_from_sdr_json(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    json_path = _make_sdr_json(tmp_path)

    from aa_auto_sdr.cli.commands import push_to_notion as pt_mod

    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "new-page"}
    mock_client.blocks.children.append.return_value = {}

    Client_factory = MagicMock(return_value=mock_client)
    with patch.object(pt_mod, "_require_notion_client", return_value=Client_factory):
        exit_code = pt_mod.run_push_to_notion(
            str(json_path),
            output_dir=str(tmp_path),
            force_new=False,
        )

    assert exit_code == 0
    mock_client.pages.create.assert_called_once()


def test_push_to_notion_from_snapshot_envelope(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    snap_path = _make_snapshot_envelope(tmp_path)

    from aa_auto_sdr.cli.commands import push_to_notion as pt_mod

    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "new-page"}
    mock_client.blocks.children.append.return_value = {}

    Client_factory = MagicMock(return_value=mock_client)
    with patch.object(pt_mod, "_require_notion_client", return_value=Client_factory):
        exit_code = pt_mod.run_push_to_notion(
            str(snap_path),
            output_dir=str(tmp_path),
            force_new=False,
        )

    assert exit_code == 0
    mock_client.pages.create.assert_called_once()


def test_push_to_notion_file_not_found_exits_1(tmp_path, capsys):
    from aa_auto_sdr.cli.commands.push_to_notion import run_push_to_notion

    code = run_push_to_notion(
        str(tmp_path / "nope.json"),
        output_dir=str(tmp_path),
        force_new=False,
    )
    assert code == 1
    assert "file not found" in capsys.readouterr().err.lower()


def test_push_to_notion_invalid_json_exits_1(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json}")
    from aa_auto_sdr.cli.commands.push_to_notion import run_push_to_notion

    code = run_push_to_notion(
        str(bad),
        output_dir=str(tmp_path),
        force_new=False,
    )
    assert code == 1
    assert "invalid json" in capsys.readouterr().err.lower()


def test_push_to_notion_unknown_shape_exits_1(tmp_path, capsys):
    weird = tmp_path / "weird.json"
    weird.write_text(json.dumps({"hello": "world"}))
    from aa_auto_sdr.cli.commands.push_to_notion import run_push_to_notion

    code = run_push_to_notion(
        str(weird),
        output_dir=str(tmp_path),
        force_new=False,
    )
    assert code == 1
    assert "unrecognized" in capsys.readouterr().err.lower()


def test_push_to_notion_force_new_creates_fresh_page(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    json_path = _make_sdr_json(tmp_path)
    # Pre-existing registry entry
    (tmp_path / ".notion_pages.json").write_text(json.dumps({"examplersid1": "old"}))

    from aa_auto_sdr.cli.commands import push_to_notion as pt_mod

    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "fresh-page"}
    Client_factory = MagicMock(return_value=mock_client)

    with patch.object(pt_mod, "_require_notion_client", return_value=Client_factory):
        exit_code = pt_mod.run_push_to_notion(
            str(json_path),
            output_dir=str(tmp_path),
            force_new=True,
        )

    assert exit_code == 0
    mock_client.pages.create.assert_called_once()
    reg = json.loads((tmp_path / ".notion_pages.json").read_text())
    # old page id moved to superseded; current points to fresh page
    entry = reg["examplersid1"]
    assert entry["current"] == "fresh-page"
    assert entry["superseded"] == ["old"]


# --- v1.19.0: registry-database threading on the push path ---


def test_push_threads_database_upsert_when_configured(tmp_path, monkeypatch):
    """Push path upserts a registry row when the database is configured (env)."""
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    monkeypatch.setenv("NOTION_REGISTRY_DATABASE_ID", "db-id")
    json_path = _make_sdr_json(tmp_path)

    from aa_auto_sdr.cli.commands import push_to_notion as pt_mod

    mock_client = MagicMock()
    mock_client.pages.create.side_effect = [{"id": "page-1"}, {"id": "row-1"}]
    mock_client.blocks.children.list.return_value = {"results": [], "has_more": False}
    mock_client.databases.retrieve.return_value = {"data_sources": [{"id": "ds-1", "name": "ds"}]}
    mock_client.data_sources.retrieve.return_value = {
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
    mock_client.data_sources.query.return_value = {"results": []}
    Client_factory = MagicMock(return_value=mock_client)

    with patch.object(pt_mod, "_require_notion_client", return_value=Client_factory):
        exit_code = pt_mod.run_push_to_notion(
            str(json_path),
            output_dir=str(tmp_path),
            force_new=False,
            notion_registry_database=None,  # use env
            no_notion_registry=False,
        )

    assert exit_code == 0
    mock_client.databases.retrieve.assert_called_once_with(database_id="db-id")


def test_push_skips_database_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    monkeypatch.setenv("NOTION_REGISTRY_DATABASE_ID", "db-id")
    json_path = _make_sdr_json(tmp_path)

    from aa_auto_sdr.cli.commands import push_to_notion as pt_mod

    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "page-1"}
    mock_client.blocks.children.list.return_value = {"results": [], "has_more": False}
    Client_factory = MagicMock(return_value=mock_client)

    with patch.object(pt_mod, "_require_notion_client", return_value=Client_factory):
        exit_code = pt_mod.run_push_to_notion(
            str(json_path),
            output_dir=str(tmp_path),
            force_new=False,
            notion_registry_database=None,
            no_notion_registry=True,
        )

    assert exit_code == 0
    mock_client.databases.retrieve.assert_not_called()


# --- v1.20.0: company threading on the push path ---


def test_push_threads_company_to_upsert_row(tmp_path, monkeypatch):
    """notion_company is resolved and forwarded as company= to upsert_row_from_dict."""
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    monkeypatch.setenv("NOTION_REGISTRY_DATABASE_ID", "db-id")
    monkeypatch.delenv("NOTION_REGISTRY_COMPANY", raising=False)
    json_path = _make_sdr_json(tmp_path)

    from aa_auto_sdr.cli.commands import push_to_notion as pt_mod

    captured: dict = {}

    def fake_upsert_from_dict(client, **kwargs):
        captured.update(kwargs)
        return "row-1"

    mock_client = MagicMock()
    mock_client.pages.create.side_effect = [{"id": "page-1"}, {"id": "row-1"}]
    mock_client.blocks.children.list.return_value = {"results": [], "has_more": False}
    Client_factory = MagicMock(return_value=mock_client)

    with (
        patch.object(pt_mod, "_require_notion_client", return_value=Client_factory),
        patch.object(pt_mod, "upsert_row_from_dict", fake_upsert_from_dict),
    ):
        exit_code = pt_mod.run_push_to_notion(
            str(json_path),
            output_dir=str(tmp_path),
            force_new=False,
            notion_registry_database="db-id",
            no_notion_registry=False,
            notion_company="acme",
        )

    assert exit_code == 0
    assert captured.get("company") == "acme"


# --- v1.20.0: publish_payload_to_notion helper is the publish path ----------


def test_publish_payload_to_notion_returns_page_id(tmp_path, monkeypatch):
    """publish_payload_to_notion returns the page id and does NOT print."""
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    payload = {
        "report_suite": {
            "rsid": "examplersid1",
            "name": "Example RS",
            "currency": "USD",
            "timezone": "America/Los_Angeles",
            "parent_rsid": None,
        },
        "captured_at": "2026-05-14T10:00:00+00:00",
        "tool_version": "1.20.0",
        "dimensions": [],
        "metrics": [],
        "segments": [],
        "calculated_metrics": [],
        "virtual_report_suites": [],
        "classifications": [],
        "fetch_status": {},
        "quality": None,
    }
    from aa_auto_sdr.cli.commands import push_to_notion as pt_mod
    from aa_auto_sdr.output.notion_registry import get_registry_path

    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "new-page-123"}
    mock_client.blocks.children.append.return_value = {}

    page_id = pt_mod.publish_payload_to_notion(
        mock_client,
        payload,
        parent_page_id="parent-id",
        registry_path=get_registry_path(tmp_path),
        force_new=False,
        database_id=None,
        disable_registry=True,  # skip DB upsert for this test
        company=None,
    )

    assert page_id == "new-page-123"
    mock_client.pages.create.assert_called_once()


def test_run_push_to_notion_uses_publish_payload_helper(tmp_path, monkeypatch, capsys):
    """run_push_to_notion delegates to publish_payload_to_notion and prints the page url."""
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    json_path = _make_sdr_json(tmp_path)

    from aa_auto_sdr.cli.commands import push_to_notion as pt_mod

    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "delegated-page"}
    mock_client.blocks.children.append.return_value = {}
    Client_factory = MagicMock(return_value=mock_client)

    with patch.object(pt_mod, "_require_notion_client", return_value=Client_factory):
        exit_code = pt_mod.run_push_to_notion(
            str(json_path),
            output_dir=str(tmp_path),
            force_new=False,
            no_notion_registry=True,
        )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "notion://pages/delegated-page" in out


def test_publish_payload_to_notion_db_error_warns_and_continues(tmp_path, monkeypatch):
    """A DB upsert failure in publish_payload_to_notion still returns the page id."""
    from aa_auto_sdr.cli.commands import push_to_notion as pt_mod
    from aa_auto_sdr.output.notion_registry import get_registry_path

    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "page-abc"}
    mock_client.blocks.children.append.return_value = {}

    def _boom_upsert(client, **kwargs):
        raise RuntimeError("DB unavailable")

    with patch.object(pt_mod, "upsert_row_from_dict", _boom_upsert):
        page_id = pt_mod.publish_payload_to_notion(
            mock_client,
            {
                "report_suite": {
                    "rsid": "testrsid",
                    "name": "Test",
                    "currency": "USD",
                    "timezone": "UTC",
                    "parent_rsid": None,
                },
                "captured_at": "2026-05-14T10:00:00+00:00",
                "tool_version": "1.20.0",
                "dimensions": [],
                "metrics": [],
                "segments": [],
                "calculated_metrics": [],
                "virtual_report_suites": [],
                "classifications": [],
                "fetch_status": {},
                "quality": None,
            },
            parent_page_id="parent-id",
            registry_path=get_registry_path(tmp_path),
            force_new=False,
            database_id="db-id",
            disable_registry=False,
            company=None,
        )

    # Despite DB failure, we still get the page id back.
    assert page_id == "page-abc"


def test_publish_payload_notion_registry_error_warns_and_continues(tmp_path):
    """A NotionRegistryError (schema mismatch) WARNs and still returns the page id."""
    from aa_auto_sdr.cli.commands import push_to_notion as pt_mod
    from aa_auto_sdr.output.notion_database import NotionRegistryError
    from aa_auto_sdr.output.notion_registry import get_registry_path

    mock_client = MagicMock()
    mock_client.pages.create.return_value = {"id": "page-xyz"}
    mock_client.blocks.children.append.return_value = {}

    def _raise_registry(client, **kwargs):
        raise NotionRegistryError("registry schema mismatch")

    with patch.object(pt_mod, "upsert_row_from_dict", _raise_registry):
        page_id = pt_mod.publish_payload_to_notion(
            mock_client,
            {
                "report_suite": {
                    "rsid": "testrsid",
                    "name": "Test",
                    "currency": "USD",
                    "timezone": "UTC",
                    "parent_rsid": None,
                },
                "captured_at": "2026-05-14T10:00:00+00:00",
                "tool_version": "1.20.0",
                "dimensions": [],
                "metrics": [],
                "segments": [],
                "calculated_metrics": [],
                "virtual_report_suites": [],
                "classifications": [],
                "fetch_status": {},
                "quality": None,
            },
            parent_page_id="parent-id",
            registry_path=get_registry_path(tmp_path),
            force_new=False,
            database_id="db-id",
            disable_registry=False,
            company=None,
        )

    # Schema-mismatch on the registry must not sink the push.
    assert page_id == "page-xyz"


def test_run_push_to_notion_publish_value_error_guarded(tmp_path, monkeypatch, capsys):
    """If publish_payload_to_notion raises ValueError, run_push_to_notion guards it."""
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    json_path = _make_sdr_json(tmp_path)

    from aa_auto_sdr.cli.commands import push_to_notion as pt_mod

    Client_factory = MagicMock(return_value=MagicMock())
    with (
        patch.object(pt_mod, "_require_notion_client", return_value=Client_factory),
        patch.object(pt_mod, "publish_payload_to_notion", side_effect=ValueError("bad shape")),
    ):
        code = pt_mod.run_push_to_notion(
            str(json_path),
            output_dir=str(tmp_path),
            force_new=False,
        )

    assert code == 1
    assert "unrecognized" in capsys.readouterr().err.lower()
