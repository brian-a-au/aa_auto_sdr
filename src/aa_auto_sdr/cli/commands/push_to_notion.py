"""``--push-to-notion`` command handler.

Reads an SDR JSON artifact (``JsonWriter`` output) or snapshot envelope
and publishes it to Notion without re-calling the AA API.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

from aa_auto_sdr.core.exit_codes import ExitCode
from aa_auto_sdr.output.notion_blocks import build_blocks_from_dict
from aa_auto_sdr.output.notion_client_guard import (
    _require_notion_client,
    resolve_notion_credentials,
    resolve_notion_database_id,
)
from aa_auto_sdr.output.notion_database import (
    NotionRegistryError,
    upsert_row_from_dict,
)
from aa_auto_sdr.output.notion_registry import get_registry_path
from aa_auto_sdr.output.writers.notion import _create_or_update_page

logger = logging.getLogger(__name__)


def _extract_rsid_and_title(payload: dict) -> tuple[str, str]:
    """Return ``(rsid, page_title)`` from either SDR JSON output or a snapshot envelope.

    SDR JSON: ``report_suite`` at top level.

    Snapshot envelope (``aa-sdr-snapshot/v*``): ``rsid`` at top level;
    ``report_suite`` (if present, with ``name``) nested under
    ``components``.
    """
    schema = payload.get("schema")
    if isinstance(schema, str) and schema.startswith("aa-sdr-snapshot/"):
        rsid = payload.get("rsid")
        rs = (payload.get("components") or {}).get("report_suite") or {}
        name = rs.get("name") or rsid
    else:
        rs = payload.get("report_suite") or {}
        rsid = rs.get("rsid")
        name = rs.get("name") or rsid
    if not rsid:
        raise ValueError("Payload has no rsid — cannot determine target page")
    return rsid, f"{name} ({rsid}) — SDR"


def run_push_to_notion(
    json_file: str,
    output_dir: str | None,
    force_new: bool,
    *,
    notion_registry_database: str | None = None,
    no_notion_registry: bool = False,
) -> int:
    path = Path(json_file)
    if not path.exists():
        print(
            f"error: --push-to-notion: file not found: {json_file}",
            file=sys.stderr,
        )
        return int(ExitCode.GENERIC)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(
            f"error: --push-to-notion: invalid JSON in {json_file}: {exc}",
            file=sys.stderr,
        )
        return int(ExitCode.GENERIC)

    try:
        blocks = build_blocks_from_dict(payload)
        rsid, page_title = _extract_rsid_and_title(payload)
    except (ValueError, KeyError) as exc:
        print(
            f"error: --push-to-notion: unrecognized payload shape in {json_file}: {exc}",
            file=sys.stderr,
        )
        return int(ExitCode.GENERIC)

    Client = _require_notion_client()
    token, parent_page_id = resolve_notion_credentials()

    effective_output_dir = Path(output_dir) if output_dir else path.parent
    registry_path = get_registry_path(effective_output_dir)

    started = time.monotonic()
    client = Client(auth=token)
    page_id = _create_or_update_page(
        client,
        parent_page_id,
        page_title,
        rsid,
        blocks,
        registry_path,
        force_new=force_new,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "push_to_notion page=notion://pages/%s duration_ms=%s rsid=%s",
        page_id,
        duration_ms,
        rsid,
        extra={
            "format": "notion",
            "notion_page_id": page_id,
            "duration_ms": duration_ms,
            "rsid": rsid,
        },
    )
    print(f"notion://pages/{page_id}")

    # v1.19.0 — opt-in registry database upsert. Same partial-failure rule as
    # the writer path: detail page is primary; DB errors WARN and continue.
    database_id = resolve_notion_database_id(
        cli_override=notion_registry_database,
        disabled=no_notion_registry,
    )
    if database_id is not None:
        db_started = time.monotonic()
        try:
            row_id = upsert_row_from_dict(
                client,
                database_id=database_id,
                rsid=rsid,
                detail_page_id=page_id,
                payload_dict=payload,
            )
            db_duration_ms = int((time.monotonic() - db_started) * 1000)
            logger.info(
                "notion_registry_upserted rsid=%s row=%s duration_ms=%s",
                rsid,
                row_id,
                db_duration_ms,
                extra={"rsid": rsid, "notion_row_id": row_id, "duration_ms": db_duration_ms},
            )
        except NotionRegistryError as exc:
            logger.warning(
                "notion_registry_unavailable rsid=%s reason=schema_mismatch detail=%s",
                rsid,
                exc,
            )
        except Exception as exc:  # DB failure must not sink the push
            logger.warning(
                "notion_registry_unavailable rsid=%s reason=%s detail=%s",
                rsid,
                type(exc).__name__,
                exc,
            )

    return int(ExitCode.OK)
