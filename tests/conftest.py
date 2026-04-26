"""Pytest fixtures and auto-marker classification."""

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-apply `unit` marker to anything not otherwise marked."""
    other_markers = {"integration", "smoke", "e2e"}
    for item in items:
        if not any(m.name in other_markers for m in item.iter_markers()):
            item.add_marker(pytest.mark.unit)
