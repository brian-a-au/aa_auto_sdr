"""Notion client import guard + credential resolution.

Isolated in its own module so tests can patch a single function
(``_require_notion_client``) regardless of whether ``notion-client`` is
installed in the test environment.
"""

from __future__ import annotations

import os
import sys
from typing import Any


def _require_notion_client() -> Any:
    """Return the ``notion_client.Client`` class or exit 1 with install instructions."""
    try:
        from notion_client import Client

        return Client
    except ImportError:
        print(
            "Error: Notion output requires the notion extra.\nInstall it with: uv pip install 'aa-auto-sdr[notion]'",
            file=sys.stderr,
        )
        sys.exit(1)


def resolve_notion_credentials() -> tuple[str, str]:
    """Return ``(NOTION_TOKEN, NOTION_PARENT_PAGE_ID)``, or exit 1 if missing.

    Resolution order: environment variable → ``.env`` file (if
    ``python-dotenv`` is installed) → hard failure.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    token = os.environ.get("NOTION_TOKEN")
    if not token:
        print(
            "Error: NOTION_TOKEN is not set. Set it as an environment variable or add it to a .env file.",
            file=sys.stderr,
        )
        sys.exit(1)

    parent_page_id = os.environ.get("NOTION_PARENT_PAGE_ID")
    if not parent_page_id:
        print(
            "Error: NOTION_PARENT_PAGE_ID is not set. Set it as an environment variable or add it to a .env file.",
            file=sys.stderr,
        )
        sys.exit(1)

    return token, parent_page_id


def resolve_notion_database_id(
    *,
    cli_override: str | None,
    disabled: bool,
) -> str | None:
    """Return the configured Notion registry database ID or ``None``.

    Resolution order:

    1. ``disabled=True`` short-circuits to ``None`` regardless of env / flag.
    2. ``cli_override`` (from ``--notion-registry-database``) wins over env.
    3. ``NOTION_REGISTRY_DATABASE_ID`` env var (or ``.env`` file).
    4. ``None`` — caller skips database upsert (v1.18.0 behavior).
    """
    if disabled:
        return None
    if cli_override:
        return cli_override
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    return os.environ.get("NOTION_REGISTRY_DATABASE_ID") or None


def resolve_notion_company(cli_override: str | None, aa_company_id: str | None) -> str:
    """Return the Company value for the registry row.

    Precedence: ``--notion-company`` flag, then ``NOTION_REGISTRY_COMPANY``
    env (or .env), then the Adobe global company id (generate path only),
    else empty string.
    """
    if cli_override:
        return cli_override
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    env = os.environ.get("NOTION_REGISTRY_COMPANY")
    if env:
        return env
    return aa_company_id or ""
