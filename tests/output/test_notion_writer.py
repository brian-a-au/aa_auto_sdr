"""Tests for NotionWriter, credential resolution, and API layer."""

from __future__ import annotations

import pytest

from aa_auto_sdr.output.notion_client_guard import resolve_notion_credentials


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
