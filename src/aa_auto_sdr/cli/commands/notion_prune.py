"""``--notion-prune-orphans`` command handler.

Archives Notion pages tombstoned by --notion-force-new. Preview by default;
``--yes`` archives.
"""

from __future__ import annotations

import logging
from pathlib import Path

from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.output.notion_client_guard import _require_notion_client, resolve_notion_token
from aa_auto_sdr.output.notion_prune import archive_orphans, collect_orphans
from aa_auto_sdr.output.notion_registry import get_registry_path, load_registry

logger = logging.getLogger(__name__)


def _is_notion_not_found(exc: BaseException) -> bool:
    """Return True only for a genuine Notion 'object not found' error.

    Notion raises ``APIResponseError`` for ALL HTTP failures (401, 403, 429,
    5xx, …).  Treating every ``APIResponseError`` as not-found would silently
    drop tombstones on transient or auth errors.  Only the ``object_not_found``
    error code means the page is genuinely gone.
    """
    try:
        from notion_client.errors import APIResponseError
    except ImportError:
        return False
    return isinstance(exc, APIResponseError) and getattr(exc, "code", None) == "object_not_found"


def run_notion_prune_orphans(output_dir: str | None, dry_run: bool) -> int:
    registry_path = get_registry_path(output_dir) if output_dir else get_registry_path(Path.cwd())
    orphans = collect_orphans(load_registry(registry_path))

    if not orphans:
        print("No orphaned Notion pages found.")
        return int(ExitCode.OK)

    if dry_run:
        print(f"DRY RUN — would archive {len(orphans)} orphaned page(s):")
        for rsid, page_id in orphans:
            print(f"  - {rsid}: {page_id}")
        print("(nothing changed; add --yes to archive)")
        return int(ExitCode.OK)

    Client = _require_notion_client()
    token = resolve_notion_token()
    client = Client(auth=token)

    result = archive_orphans(client, registry_path, orphans, dry_run=False, is_not_found=_is_notion_not_found)
    print(f"Archived {len(result.archived)} page(s); {len(result.failed)} failed.")
    return int(ExitCode.OK)
