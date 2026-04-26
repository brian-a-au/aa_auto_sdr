"""Format → Writer registry with alias resolution.

Writer-existence tests live in test_writer_json.py and test_writer_excel.py;
this file covers only the registry contract."""

from pathlib import Path
from typing import Any

import pytest

from aa_auto_sdr.output import registry


@pytest.fixture(autouse=True)
def _isolate_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset _WRITERS so tests in this module don't leak into one another."""
    monkeypatch.setattr(registry, "_WRITERS", {})


def test_unknown_format_raises() -> None:
    with pytest.raises(KeyError):
        registry.resolve_formats("nonsense")


def test_concrete_format_resolves_to_self() -> None:
    assert registry.resolve_formats("json") == ["json"]


def test_alias_all_resolves_to_five_formats() -> None:
    assert set(registry.resolve_formats("all")) == {"excel", "csv", "json", "html", "markdown"}


def test_alias_reports_resolves_to_excel_markdown() -> None:
    assert set(registry.resolve_formats("reports")) == {"excel", "markdown"}


def test_alias_data_resolves_to_csv_json() -> None:
    assert set(registry.resolve_formats("data")) == {"csv", "json"}


def test_alias_ci_resolves_to_json_markdown() -> None:
    assert set(registry.resolve_formats("ci")) == {"json", "markdown"}


def test_register_writer_then_get_writer_round_trip() -> None:
    class _Stub:
        extension = ".stub"

        def write(self, doc: Any, output_path: Path) -> Path:
            return output_path

    registry.register_writer("stub", _Stub())
    assert isinstance(registry.get_writer("stub"), _Stub)


def test_get_writer_unknown_raises() -> None:
    with pytest.raises(KeyError):
        registry.get_writer("not-registered")
