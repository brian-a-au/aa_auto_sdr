"""Archive Notion pages tombstoned in the local registry (--notion-prune-orphans).

A tombstoned page is one an RSID was repointed away from by --notion-force-new.
Pruning archives those pages (moves them to Notion trash, recoverable) and
removes them from the registry's superseded list.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aa_auto_sdr.output.notion_registry import collect_superseded, drop_superseded

logger = logging.getLogger(__name__)


@dataclass
class PruneResult:
    planned: list[tuple[str, str]] = field(default_factory=list)
    archived: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str, str]] = field(default_factory=list)


def collect_orphans(registry: dict[str, dict]) -> list[tuple[str, str]]:
    return collect_superseded(registry)


def archive_orphans(
    client: Any,
    registry_path: Path,
    orphans: list[tuple[str, str]],
    *,
    dry_run: bool,
    is_not_found: Callable[[BaseException], bool] | None = None,
) -> PruneResult:
    """Archive tombstoned Notion pages and clean up the registry.

    ``is_not_found`` is an optional predicate that returns ``True`` only for
    genuine "page not found" errors (e.g. Notion's ``object_not_found`` code).
    When it returns ``True`` the page is treated as already-gone: the tombstone
    is dropped and the page is counted as archived.  Any other exception keeps
    the tombstone and records the failure — preventing transient/auth errors
    (which Notion also raises as ``APIResponseError``) from silently destroying
    tombstone entries.
    """
    _is_not_found = is_not_found if is_not_found is not None else (lambda _e: False)
    result = PruneResult(planned=list(orphans))
    if dry_run:
        logger.info("notion_prune_planned count=%d", len(orphans))
        return result
    for rsid, page_id in orphans:
        try:
            client.pages.update(page_id=page_id, archived=True)
        except Exception as exc:
            if _is_not_found(exc):
                # Page already gone — the goal is met; drop the tombstone.
                drop_superseded(registry_path, rsid, page_id)
                result.archived.append((rsid, page_id))
                logger.info("notion_page_archived rsid=%s page=%s (already gone)", rsid, page_id)
            else:
                # Keep the tombstone so prune can be retried after the error clears.
                result.failed.append((rsid, page_id, type(exc).__name__))
                logger.warning(
                    "notion_page_archive_failed rsid=%s page=%s reason=%s", rsid, page_id, type(exc).__name__
                )
            continue
        drop_superseded(registry_path, rsid, page_id)
        result.archived.append((rsid, page_id))
        logger.info("notion_page_archived rsid=%s page=%s", rsid, page_id)
    logger.info("notion_prune_complete archived=%d failed=%d", len(result.archived), len(result.failed))
    return result
