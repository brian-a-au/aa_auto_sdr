"""Notion output writer. Self-registers with the registry on import.

Credentials are env vars only (not in profile ``config.json``):

* ``NOTION_TOKEN`` — Notion internal integration token
* ``NOTION_PARENT_PAGE_ID`` — Parent page under which SDR pages are created

Install the optional dep: ``uv pip install 'aa-auto-sdr[notion]'``.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from aa_auto_sdr.output.notion_blocks import build_blocks_from_document
from aa_auto_sdr.output.notion_client_guard import (
    _require_notion_client,
    resolve_notion_credentials,
    resolve_notion_database_id,
)
from aa_auto_sdr.output.notion_database import (
    NotionRegistryError,
    upsert_row,
)
from aa_auto_sdr.output.notion_registry import (
    get_registry_path,
    lookup_page_id,
    store_page_id,
)
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)


def _clear_page_blocks(client: Any, page_id: str) -> None:
    """Delete all child blocks from a Notion page (no bulk-clear API).

    Two-pass: collect every block id by paginating ``blocks.children.list``,
    then delete. Listing and deleting in the same pass risks invalidating
    the pagination cursor on archive-style deletes.
    """
    ids: list[str] = []
    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {"block_id": page_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = client.blocks.children.list(**kwargs)
        ids.extend(b["id"] for b in response.get("results", []))
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    for block_id in ids:
        client.blocks.delete(block_id=block_id)


def _append_blocks(client: Any, page_id: str, blocks: list[dict], batch_size: int = 100) -> None:
    for i in range(0, len(blocks), batch_size):
        client.blocks.children.append(
            block_id=page_id,
            children=blocks[i : i + batch_size],
        )


def _create_or_update_page(
    client: Any,
    parent_page_id: str,
    page_title: str,
    rsid: str,
    blocks: list[dict],
    registry_path: Path,
    *,
    force_new: bool,
) -> str:
    existing = None if force_new else lookup_page_id(registry_path, rsid)

    if existing:
        _clear_page_blocks(client, existing)
        _append_blocks(client, existing, blocks)
        store_page_id(registry_path, rsid, existing)
        return existing

    # Notion expects the parent-page title to be a fully-shaped `title` property
    # object — the bare rich-text array form is rejected on `pages.create`.
    page = client.pages.create(
        parent={"page_id": parent_page_id},
        properties={
            "title": {
                "title": [{"type": "text", "text": {"content": page_title}}],
            },
        },
    )
    page_id = page["id"]
    _append_blocks(client, page_id, blocks)
    store_page_id(registry_path, rsid, page_id)
    return page_id


class NotionWriter:
    """Writer that publishes an :class:`SdrDocument` to a Notion page.

    Returns ``[registry_path]`` — the ``.notion_pages.json`` file written
    — to satisfy the :class:`Writer` protocol's ``list[Path]`` contract.
    The Notion page identifier is logged but is **not** returned as a
    path (it lives in Notion, not on disk).

    ``force_new`` is a per-run instance attribute mutated by
    :mod:`aa_auto_sdr.pipeline.single` before ``write()`` is called —
    mirrors how ``excel-template`` threads ``template_path`` /
    ``template_organization`` (see the ``"notion" in formats`` block in
    ``pipeline/single.py``).
    Defaulted to False on the registered singleton.
    """

    extension = ".notion"  # nominal; the file is never created on disk
    force_new: bool = False  # set per-run by pipeline/single.py
    # v1.19.0 — registry database threading (set per-run by pipeline/single.py,
    # same singleton-mutation pattern as force_new). Resolved in write() via
    # resolve_notion_database_id().
    database_id: str | None = None
    disable_registry: bool = False

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        started = time.monotonic()
        Client = _require_notion_client()
        token, parent_page_id = resolve_notion_credentials()

        rsid = doc.report_suite.rsid
        name = doc.report_suite.name or rsid
        page_title = f"{name} ({rsid}) — SDR"
        blocks = build_blocks_from_document(doc)

        # output_path is a synthetic <rsid>.notion path; we never create it
        # on disk. The registry lives in its parent dir (i.e. --output-dir).
        registry_path = get_registry_path(output_path.parent)

        client = Client(auth=token)
        page_id = _create_or_update_page(
            client,
            parent_page_id,
            page_title,
            rsid,
            blocks,
            registry_path,
            force_new=self.force_new,
        )

        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "output_write format=notion page=notion://pages/%s duration_ms=%s",
            page_id,
            duration_ms,
            extra={
                "format": "notion",
                "notion_page_id": page_id,
                "output_path": str(registry_path),
                "count": 1,
                "duration_ms": duration_ms,
                "rsid": rsid,
            },
        )

        # v1.19.0 — opt-in registry database upsert. The detail page is the
        # primary artifact; any database failure logs a WARN and is swallowed
        # so the run does not fail.
        database_id = resolve_notion_database_id(
            cli_override=self.database_id,
            disabled=self.disable_registry,
        )
        if database_id is not None:
            db_started = time.monotonic()
            try:
                row_id = upsert_row(
                    client,
                    database_id=database_id,
                    rsid=rsid,
                    detail_page_id=page_id,
                    doc=doc,
                )
                db_duration_ms = int((time.monotonic() - db_started) * 1000)
                logger.info(
                    "notion_registry_upserted rsid=%s row=%s duration_ms=%s",
                    rsid,
                    row_id,
                    db_duration_ms,
                    extra={
                        "rsid": rsid,
                        "notion_row_id": row_id,
                        "duration_ms": db_duration_ms,
                    },
                )
            except NotionRegistryError as exc:
                logger.warning(
                    "notion_registry_unavailable rsid=%s reason=schema_mismatch detail=%s",
                    rsid,
                    exc,
                )
            except Exception as exc:  # DB failure must not sink the detail page
                logger.warning(
                    "notion_registry_unavailable rsid=%s reason=%s detail=%s",
                    rsid,
                    type(exc).__name__,
                    exc,
                )
        else:
            logger.debug("notion_registry_skipped rsid=%s reason=no_database_id", rsid)

        return [registry_path]


register_writer("notion", NotionWriter())
