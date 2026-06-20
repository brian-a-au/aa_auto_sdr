"""Archive Notion pages tombstoned in the local registry (--notion-prune-orphans).

A tombstoned page is one an RSID was repointed away from by --notion-force-new.
Pruning archives those pages (moves them to Notion trash, recoverable) and
removes them from the registry's superseded list.
"""

from __future__ import annotations

import logging
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
    not_found_types: tuple[type[Exception], ...] = (),
) -> PruneResult:
    result = PruneResult(planned=list(orphans))
    if dry_run:
        logger.info("notion_prune_planned count=%d", len(orphans))
        return result
    for rsid, page_id in orphans:
        try:
            client.pages.update(page_id=page_id, archived=True)
        except not_found_types:
            # Page already gone — the goal is met; drop the tombstone.
            drop_superseded(registry_path, rsid, page_id)
            result.archived.append((rsid, page_id))
            logger.info("notion_page_archived rsid=%s page=%s (already gone)", rsid, page_id)
            continue
        except Exception as exc:  # keep the tombstone, report the failure
            result.failed.append((rsid, page_id, type(exc).__name__))
            logger.warning("notion_page_archive_failed rsid=%s page=%s reason=%s", rsid, page_id, type(exc).__name__)
            continue
        drop_superseded(registry_path, rsid, page_id)
        result.archived.append((rsid, page_id))
        logger.info("notion_page_archived rsid=%s page=%s", rsid, page_id)
    logger.info("notion_prune_complete archived=%d failed=%d", len(result.archived), len(result.failed))
    return result
