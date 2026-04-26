"""Argparse surface for v0.1.

Only flags shippable in v0.1 are defined here. Discovery, inspection, batch,
and diff flags land in v0.3+ in their own milestones."""

from __future__ import annotations

import argparse
from pathlib import Path

_VALID_FORMATS = ["excel", "csv", "json", "html", "markdown", "all", "reports", "data", "ci"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aa_auto_sdr",
        description="Adobe Analytics SDR Generator (API 2.0 only)",
    )
    p.add_argument(
        "rsid",
        nargs="?",
        default=None,
        help="Report Suite ID to generate an SDR for",
    )
    p.add_argument(
        "--format",
        choices=_VALID_FORMATS,
        default="excel",
        help="Output format or alias (default: excel)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory to write outputs into (default: cwd)",
    )
    p.add_argument(
        "--profile",
        default=None,
        help="Use a named credentials profile from ~/.aa/orgs/<name>/",
    )
    p.add_argument(
        "--profile-add",
        metavar="NAME",
        default=None,
        help="Create or update a credentials profile interactively",
    )
    p.add_argument(
        "--show-config",
        action="store_true",
        help="Print which credential source resolved and exit",
    )
    return p
