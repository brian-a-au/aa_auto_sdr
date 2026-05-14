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
            "Error: Notion output requires the notion extra.\n"
            "Install it with: uv pip install 'aa-auto-sdr[notion]'",
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
            "Error: NOTION_TOKEN is not set. "
            "Set it as an environment variable or add it to a .env file.",
            file=sys.stderr,
        )
        sys.exit(1)

    parent_page_id = os.environ.get("NOTION_PARENT_PAGE_ID")
    if not parent_page_id:
        print(
            "Error: NOTION_PARENT_PAGE_ID is not set. "
            "Set it as an environment variable or add it to a .env file.",
            file=sys.stderr,
        )
        sys.exit(1)

    return token, parent_page_id
