"""``--notion-repair-database`` command handler.

Compares the Notion registry database's current schema against the canonical
:data:`~aa_auto_sdr.output.notion_database.PROPERTY_SCHEMA` and either
reports what would change (``dry_run=True``) or applies the missing properties
(``dry_run=False``).

The CLI flag wiring (``--notion-repair-database``) is Task 10.  This module
only exposes the handler function.
"""

from __future__ import annotations

import logging
import sys

from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.output.notion_client_guard import (
    _require_notion_client,
    resolve_notion_token,
)
from aa_auto_sdr.output.notion_database import NotionRegistryError, repair_database

logger = logging.getLogger(__name__)


def run_notion_repair_database(database_id: str, dry_run: bool) -> int:
    """Repair the Notion registry database schema.

    When ``dry_run=True`` (the default when the user passes ``--dry-run``),
    prints a report of what would change without sending any update.
    When ``dry_run=False``, applies missing properties and logs each action.

    Returns ``ExitCode.OK`` on success, ``ExitCode.GENERIC`` on error.
    """
    Client = _require_notion_client()
    token = resolve_notion_token()
    client = Client(auth=token)

    try:
        result = repair_database(client, database_id=database_id, dry_run=dry_run)
    except NotionRegistryError as exc:
        logger.error("notion_repair_error detail=%s", exc)
        print(f"error: --notion-repair-database: {exc}")
        return int(ExitCode.GENERIC)
    except Exception as exc:
        logger.warning(
            "notion_repair_failed reason=%s detail=%s",
            type(exc).__name__,
            exc,
            extra={"reason": type(exc).__name__, "detail": str(exc)},
        )
        print(f"error: --notion-repair-database failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return int(ExitCode.GENERIC)

    if dry_run:
        logger.info("notion_repair_planned add=%d conflicts=%d", len(result.to_add), len(result.conflicts))
        print("DRY RUN — no changes will be made")
        for name in result.to_add:
            print(f"+ {name}")
        for name, want, have in result.conflicts:
            print(f"! {name}: want {want}, have {have}")
    else:
        for name in result.to_add:
            logger.info(
                "notion_property_created name=%s",
                name,
                extra={"notion_property_name": name},
            )
        for name, want, have in result.conflicts:
            logger.warning(
                "notion_repair_type_conflict name=%s want=%s have=%s",
                name,
                want,
                have,
                extra={"notion_property_name": name, "want_type": want, "have_type": have},
            )
        logger.info(
            "notion_repair_complete properties_added=%d",
            len(result.to_add),
            extra={"properties_added": len(result.to_add)},
        )

    return int(ExitCode.OK)
