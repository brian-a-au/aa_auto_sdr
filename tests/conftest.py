"""Pytest fixtures and auto-marker classification."""

import logging

import pytest


@pytest.fixture(autouse=True)
def _isolate_root_logging():
    """Undo root-logger changes a test makes, such as ``setup_logging()``.

    ``setup_logging()`` attaches a ``StreamHandler`` bound to ``sys.stderr``,
    which inside a test is that test's capture stream. Left in place, the next
    test on the same process logs through a handler whose stream pytest has
    closed, and the resulting ``--- Logging error ---`` lands in that test's
    stderr. Under pytest-xdist this depends on which tests share a worker.
    pytest's own capture handlers are left for pytest to manage.
    """
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for handler in root.handlers[:]:
        if handler not in handlers and not type(handler).__module__.startswith("_pytest"):
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)


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
