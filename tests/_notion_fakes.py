"""Shared fake Notion client helpers for Notion-related test modules.

Consolidated fakes used across:
- tests/output/test_notion_database.py
- tests/cli/test_notion_repair_command.py
- tests/cli/test_notion_prune_command.py
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# FakeRepairClient
# Consolidates _RepairClient (test_notion_database.py) and
# _FakeRepairClient (test_notion_repair_command.py).
#
# Both variants spy on data_sources.update and expose a databases.retrieve
# that returns a single data source "ds-repair".
#
# Construction:
#   FakeRepairClient()                    — all PROPERTY_SCHEMA entries present
#   FakeRepairClient(existing_props={…})  — pass a custom props dict directly
#   FakeRepairClient(missing_prop="X")    — start from all props, drop one
# ---------------------------------------------------------------------------


class FakeRepairClient:
    """Fake Notion client for repair_database and repair command tests.

    Supports two construction styles:
    * Pass ``existing_props`` directly (fine-grained control, used in
      test_notion_database.py).
    * Pass ``missing_prop`` to start from the full PROPERTY_SCHEMA and
      remove one entry (used in test_notion_repair_command.py).
    """

    def __init__(
        self,
        existing_props: dict | None = None,
        *,
        missing_prop: str | None = None,
    ):
        self.update_calls: list[dict] = []

        from aa_auto_sdr.output.notion_database import PROPERTY_SCHEMA

        if existing_props is None:
            existing_props = {name: {"type": schema["type"]} for name, schema in PROPERTY_SCHEMA.items()}
        if missing_prop:
            del existing_props[missing_prop]
        self._existing_props = existing_props

        outer = self

        class _DS:
            def retrieve(self, **kw):
                return {"properties": outer._existing_props}

            def update(self, data_source_id=None, **kw):
                outer.update_calls.append({"data_source_id": data_source_id, **kw})

        class _DBs:
            def retrieve(self, **kw):
                return {"data_sources": [{"id": "ds-repair"}]}

        self.data_sources = _DS()
        self.databases = _DBs()


# ---------------------------------------------------------------------------
# FakeRegistryClient
# Renamed from _FakeClient in test_notion_database.py.
# Full-featured fake used for _query_and_upsert tests: exposes
# data_sources (query + retrieve), databases (retrieve), and pages
# (create + update).
# ---------------------------------------------------------------------------


class FakeRegistryClient:
    """Fake Notion client for _query_and_upsert / upsert_row tests."""

    def __init__(self, existing_rows=None, db_props=None):
        self.queries = []
        self.created = []
        self.updated = []
        self._rows = existing_rows or []

        from aa_auto_sdr.output import notion_database as db

        self._db_props = db_props if db_props is not None else {k: {} for k in db.PROPERTY_SCHEMA}

        outer = self

        class _DS:
            def query(self, **kw):
                outer.queries.append(kw)
                return {"results": outer._rows}

            def retrieve(self, **kw):
                return {"properties": outer._db_props}

        class _DBs:
            def retrieve(self, **kw):
                return {"data_sources": [{"id": "ds1"}]}

        class _Pages:
            def create(self, **kw):
                outer.created.append(kw)
                return {"id": "new_row"}

            def update(self, **kw):
                outer.updated.append(kw)

        self.data_sources = _DS()
        self.databases = _DBs()
        self.pages = _Pages()


# ---------------------------------------------------------------------------
# FakePrunePages / FakePruneClient
# From test_notion_prune_command.py.
# Minimal fake used for prune command tests: only pages.update is needed.
# ---------------------------------------------------------------------------


class FakePrunePages:
    """Fake pages object that records archive calls."""

    def __init__(self):
        self.archived = []

    def update(self, *, page_id, archived):
        self.archived.append((page_id, archived))


class FakePruneClient:
    """Fake Notion client for prune command tests."""

    def __init__(self, *, auth):
        self.pages = FakePrunePages()
