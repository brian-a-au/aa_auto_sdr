"""``--notion-print-database-schema`` command handler (fast-path).

Prints the canonical Notion SDR Registry database schema to stdout and
exits. Used by operators to set up the database manually. Wired in
``__main__.py`` before pandas / aanalytics2 / notion-client are loaded
so the command is responsive even on slow imports.
"""

from __future__ import annotations

from aa_auto_sdr.output.notion_database import schema_cheatsheet


def run_notion_print_schema() -> int:
    print(schema_cheatsheet(), end="")
    return 0
