"""Pytest fixtures and auto-marker classification."""

import pytest


@pytest.fixture(autouse=True)
def _clear_notion_data_source_cache() -> None:
    """Reset the module-level Notion data-source cache before every test.

    Prevents the cache in :mod:`aa_auto_sdr.output.notion_database` from
    leaking state between tests that reuse the same database id (e.g. ``"db1"``
    or ``"db-repair"``).
    """
    try:
        from aa_auto_sdr.output.notion_database import clear_data_source_cache

        clear_data_source_cache()
    except ImportError:
        pass  # module not yet imported — nothing to clear


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-apply `unit` marker to anything not otherwise marked."""
    other_markers = {"integration", "smoke", "e2e"}
    for item in items:
        if not any(m.name in other_markers for m in item.iter_markers()):
            item.add_marker(pytest.mark.unit)
