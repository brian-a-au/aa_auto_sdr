"""Per-run logging for aa_auto_sdr.

This is the only module in src/ that imports logging.handlers or instantiates
handlers. Other modules call ``logging.getLogger(__name__)`` and trust that
``setup_logging(namespace)`` has been invoked once from ``cli/main.run()``.

Fast-path entries in ``__main__.py`` (--version, --help, --exit-codes,
--explain-exit-code, --completion) deliberately do NOT initialize logging --
they exit in milliseconds and writing a per-run file would be noise.
"""

from __future__ import annotations

import argparse
import atexit
import json  # noqa: F401 — used by JSON formatter in Task 5
import logging
import os
import re  # noqa: F401 — used by redaction filter in Task 4
import sys
import uuid
from datetime import UTC, datetime  # noqa: F401 — used by file handler in Task 3
from logging.handlers import RotatingFileHandler  # noqa: F401 — used by file handler in Task 3
from pathlib import Path
from typing import Any  # noqa: F401 — used by JSON formatter in Task 5

from aa_auto_sdr.core.version import __version__  # noqa: F401 — used by metadata header in Task 3

LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_FILE_BACKUP_COUNT = 5
VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
RUN_ID = uuid.uuid4().hex[:12]

_atexit_registered = False


def infer_run_mode(ns: argparse.Namespace) -> str:
    """Map a parsed argparse Namespace to a run-mode string.

    Returns one of: 'diff', 'batch', 'discovery', 'inspect', 'snapshot',
    'profile', 'config', 'stats', 'interactive', 'single', 'other'.
    """
    if getattr(ns, "diff", None):
        return "diff"
    if getattr(ns, "batch", None) or len(getattr(ns, "rsids", []) or []) > 1:
        return "batch"
    if getattr(ns, "list_reportsuites", False) or getattr(ns, "list_virtual_reportsuites", False):
        return "discovery"
    if (
        getattr(ns, "describe_reportsuite", None)
        or getattr(ns, "list_metrics", None)
        or getattr(ns, "list_dimensions", None)
        or getattr(ns, "list_segments", None)
        or getattr(ns, "list_calculated_metrics", None)
        or getattr(ns, "list_classification_datasets", None)
    ):
        return "inspect"
    if getattr(ns, "list_snapshots", False) or getattr(ns, "prune_snapshots", False):
        return "snapshot"
    if (
        getattr(ns, "profile_add", None)
        or getattr(ns, "profile_test", None)
        or getattr(ns, "profile_show", None)
        or getattr(ns, "profile_list", False)
        or getattr(ns, "profile_import", None)
    ):
        return "profile"
    if (
        getattr(ns, "show_config", False)
        or getattr(ns, "config_status", False)
        or getattr(ns, "validate_config", False)
        or getattr(ns, "sample_config", False)
    ):
        return "config"
    if getattr(ns, "stats", False):
        return "stats"
    if getattr(ns, "interactive", False):
        return "interactive"
    if getattr(ns, "rsids", []):
        return "single"
    return "other"


def setup_logging(
    namespace: argparse.Namespace,
    *,
    log_dir: Path = Path("logs"),  # noqa: ARG001 — used by file handler in Task 3
) -> logging.Logger:
    """Configure root logger from a parsed argparse Namespace.

    Idempotent: a second call replaces handlers cleanly. Returns the package
    logger (``aa_auto_sdr``).

    Skeleton form (Task 2): console-only handler, default level resolution.
    File handler / redaction / JSON formatter land in Tasks 3-5.
    """
    global _atexit_registered  # noqa: PLW0603 — module-level guard for atexit registration

    log_level = (getattr(namespace, "log_level", None) or os.environ.get("LOG_LEVEL", "INFO")).upper()
    if log_level not in VALID_LEVELS:
        print(f"Warning: invalid log level '{log_level}', using INFO", file=sys.stderr)  # noqa: T201
        log_level = "INFO"
    numeric_level = getattr(logging, log_level)

    for handler in logging.root.handlers[:]:
        handler.close()
        logging.root.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.setLevel(numeric_level)
    logging.root.addHandler(console)
    logging.root.setLevel(numeric_level)

    if not _atexit_registered:
        atexit.register(logging.shutdown)
        _atexit_registered = True

    logger = logging.getLogger("aa_auto_sdr")
    logger.setLevel(logging.NOTSET)
    return logger
