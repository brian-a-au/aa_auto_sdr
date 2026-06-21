"""Tests for notion_client_guard — credential resolution + company resolver."""

from __future__ import annotations

from aa_auto_sdr.output.notion_client_guard import resolve_notion_company


def test_company_flag_wins(monkeypatch):
    monkeypatch.setenv("NOTION_REGISTRY_COMPANY", "envco")
    assert resolve_notion_company("flagco", "aaco") == "flagco"


def test_company_env_over_aa(monkeypatch):
    monkeypatch.setenv("NOTION_REGISTRY_COMPANY", "envco")
    assert resolve_notion_company(None, "aaco") == "envco"


def test_company_falls_back_to_aa(monkeypatch):
    monkeypatch.delenv("NOTION_REGISTRY_COMPANY", raising=False)
    assert resolve_notion_company(None, "aaco") == "aaco"


def test_company_empty_when_nothing(monkeypatch):
    monkeypatch.delenv("NOTION_REGISTRY_COMPANY", raising=False)
    assert resolve_notion_company(None, None) == ""
