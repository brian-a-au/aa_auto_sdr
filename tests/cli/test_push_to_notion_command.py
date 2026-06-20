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
    assert reg["examplersid1"] == "fresh-page"


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
    mock_client.databases.retrieve.return_value = {
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
    mock_client.databases.query.return_value = {"results": []}
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
