"""``--notion-create-database`` command handler.

Creates the Notion SDR Registry database with the full canonical schema under
``NOTION_PARENT_PAGE_ID``, in one ``databases.create`` call. Preview by default
(prints the planned title, parent, and schema); ``--yes`` creates it and prints
the new database id to wire as ``NOTION_REGISTRY_DATABASE_ID``.

The CLI flag wiring (``--notion-create-database`` / ``--notion-database-title``)
lives in the parser and ``_dispatch``; this module only exposes the handler.
"""

from __future__ import annotations

import logging
import sys

from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.output.notion_client_guard import _require_notion_client, resolve_notion_credentials
from aa_auto_sdr.output.notion_database import create_database, schema_cheatsheet

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_TITLE = "AA SDR Registry"


def run_notion_create_database(*, title: str, dry_run: bool, registry_already_configured: bool) -> int:
    """Create the registry database (or preview the plan).

    Returns ``ExitCode.OK`` on preview/success, ``ExitCode.GENERIC`` on SDK
    error. Exits 1 via the credential guard when ``NOTION_TOKEN`` /
    ``NOTION_PARENT_PAGE_ID`` are missing.
    """
    token, parent_page_id = resolve_notion_credentials()

    if registry_already_configured:
        logger.warning(
            "notion_create_existing_registry detail=%s",
            "a registry database id is already configured; this creates an additional one",
            extra={"detail": "registry already configured"},
        )
        print(
            "warning: a registry database is already configured "
            "(NOTION_REGISTRY_DATABASE_ID / --notion-registry-database); "
            "this will create an additional one.",
            file=sys.stderr,
        )

    if dry_run:
        logger.info(
            "notion_create_planned title=%s parent=%s",
            title,
            parent_page_id,
            extra={"title": title, "parent_page_id": parent_page_id},
        )
        print("DRY RUN — would create the Notion SDR Registry database:")
        print(f"  Title:  {title}")
        print(f"  Parent: {parent_page_id}")
        print()
        print(schema_cheatsheet(), end="")
        print("(nothing created; add --yes to create)")
        return int(ExitCode.OK)

    Client = _require_notion_client()
    client = Client(auth=token)
    try:
        database_id, database_url = create_database(client, parent_page_id=parent_page_id, title=title)
    except Exception as exc:
        logger.warning(
            "notion_create_failed reason=%s detail=%s",
            type(exc).__name__,
            exc,
            extra={"reason": type(exc).__name__, "detail": str(exc)},
        )
        print(f"error: --notion-create-database failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return int(ExitCode.GENERIC)

    logger.info(
        "notion_database_created database_id=%s",
        database_id,
        extra={"database_id": database_id},
    )
    print("Created Notion SDR Registry database:")
    print(f"  Title:        {title}")
    print(f"  Database ID:  {database_id}")
    print(f"  URL:          {database_url}")
    print()
    print("Wire it up by setting:")
    print(f"  export NOTION_REGISTRY_DATABASE_ID={database_id}")
    return int(ExitCode.OK)
