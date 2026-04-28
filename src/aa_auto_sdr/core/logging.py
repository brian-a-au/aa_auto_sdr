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
import json
import logging
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from aa_auto_sdr.core.version import __version__

LOG_FILE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_FILE_BACKUP_COUNT = 5
VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
RUN_ID = uuid.uuid4().hex[:12]

_atexit_registered = False


_REDACTION_PATTERNS = (
    (re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"Authorization:\s*[^\r\n]+", re.IGNORECASE), "Authorization: [REDACTED]"),
    (re.compile(r"client_secret=[A-Za-z0-9._\-]+", re.IGNORECASE), "client_secret=[REDACTED]"),
    (re.compile(r"access_token=[A-Za-z0-9._\-]+", re.IGNORECASE), "access_token=[REDACTED]"),
    # Adobe IMS token-response shapes — surface at --log-level DEBUG via urllib3 body dumps.
    (re.compile(r"id_token=[A-Za-z0-9._\-]+", re.IGNORECASE), "id_token=[REDACTED]"),
    (re.compile(r"refresh_token=[A-Za-z0-9._\-]+", re.IGNORECASE), "refresh_token=[REDACTED]"),
    (re.compile(r"jwt[_-]?token=[A-Za-z0-9._\-]+", re.IGNORECASE), "jwt_token=[REDACTED]"),
)
_SENSITIVE_FIELDS = frozenset(
    {
        "secret",
        "client_secret",
        "access_token",
        "authorization",
        "bearer",
        "id_token",
        "refresh_token",
        "jwt_token",
    }
)
_REDACTION_SENTINEL = "[log-redaction-error]"


def _redact_text(text: str) -> str:
    try:
        for pattern, replacement in _REDACTION_PATTERNS:
            text = re.sub(pattern, replacement, text)
        return text
    except Exception:
        return _REDACTION_SENTINEL


class SensitiveDataFilter(logging.Filter):
    """Strip sensitive credentials from records before they reach handlers.

    Operates in-place on record.msg, record.args, and any record attributes
    whose name matches a known-sensitive field. A regex failure surfaces as
    the sentinel '[log-redaction-error]' rather than leaking the raw value.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact_text(record.msg)
        if record.args:
            redacted: list[Any] = []
            for arg in record.args if isinstance(record.args, tuple) else (record.args,):
                if isinstance(arg, str):
                    redacted.append(_redact_text(arg))
                else:
                    redacted.append(arg)
            record.args = tuple(redacted) if isinstance(record.args, tuple) else redacted[0]
        for attr in list(vars(record)):
            if attr in _SENSITIVE_FIELDS or attr.lower() in _SENSITIVE_FIELDS:
                setattr(record, attr, "[REDACTED]")
        return True


_RESERVED_LOGRECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime"}


class JSONFormatter(logging.Formatter):
    """NDJSON formatter: one JSON object per record, terminated with newline.

    Schema:
        {timestamp, level, logger, message, run_id, run_mode, tool_version, ...extra}
    Reserved LogRecord fields (pathname, lineno, etc.) are excluded.
    """

    def __init__(self, *, run_mode: str) -> None:
        super().__init__()
        self._run_mode = run_mode

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "run_id": RUN_ID,
            "run_mode": self._run_mode,
            "tool_version": __version__,
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_FIELDS:
                continue
            if key.startswith("_"):
                continue
            payload[key] = value
        try:
            return json.dumps(payload, default=str)
        except (TypeError, ValueError):  # fmt: skip
            return json.dumps(
                {
                    "timestamp": payload["timestamp"],
                    "level": payload["level"],
                    "logger": payload["logger"],
                    "message": "[json-format-error]",
                    "run_id": RUN_ID,
                    "run_mode": self._run_mode,
                    "tool_version": __version__,
                }
            )


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


def _log_filename(run_mode: str, ns: argparse.Namespace, ts: str) -> str:
    """Map run mode + namespace to log filename (no path prefix)."""
    if run_mode == "single":
        rsids = getattr(ns, "rsids", []) or []
        if rsids:
            return f"SDR_Generation_{rsids[0]}_{ts}.log"
    if run_mode == "batch":
        return f"SDR_Batch_Generation_{ts}.log"
    if run_mode == "diff":
        return f"SDR_Diff_{ts}.log"
    return f"SDR_Run_{ts}.log"


def setup_logging(
    namespace: argparse.Namespace,
    *,
    log_dir: Path = Path("logs"),
) -> logging.Logger:
    """Configure root logger from a parsed argparse Namespace.

    Idempotent: a second call replaces handlers cleanly. Returns the package
    logger (``aa_auto_sdr``).

    Wires a stderr console handler plus a best-effort ``RotatingFileHandler``
    whose filename is run-mode-aware. If the log directory cannot be created
    (PermissionError / OSError) the file handler is skipped and a warning is
    emitted on stderr — the run continues with console-only logging.
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

    run_mode = infer_run_mode(namespace)
    log_format = getattr(namespace, "log_format", "text")
    if log_format == "json":
        formatter: logging.Formatter = JSONFormatter(run_mode=run_mode)
    else:
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Best-effort log directory creation.
    log_file: Path | None = None
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / _log_filename(run_mode, namespace, ts)
    except (PermissionError, OSError) as exc:
        print(  # noqa: T201
            f"Warning: Cannot create logs directory: {exc}. Logging to console only.",
            file=sys.stderr,
        )

    # Console handler — stderr, not stdout.
    quiet = bool(getattr(namespace, "quiet", False))
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    console.setLevel(logging.WARNING if quiet else numeric_level)
    console.addFilter(SensitiveDataFilter())
    logging.root.addHandler(console)

    # File handler — best-effort.
    if log_file is not None:
        fh = RotatingFileHandler(log_file, maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUP_COUNT)
        fh.setFormatter(formatter)
        fh.setLevel(numeric_level)
        fh.addFilter(SensitiveDataFilter())
        logging.root.addHandler(fh)

    logging.root.setLevel(numeric_level)

    if not _atexit_registered:
        atexit.register(logging.shutdown)
        _atexit_registered = True

    logger = logging.getLogger("aa_auto_sdr")
    logger.setLevel(logging.NOTSET)

    # Startup banner — five INFO records, always emitted (file handler always
    # captures them; console may suppress under --quiet).
    if log_file is not None:
        logger.info("Logging initialized. Log file: %s", log_file)
    else:
        logger.info("Logging initialized. Console output only.")
    logger.info("aa_auto_sdr version: %s", __version__)
    logger.info("Python %s on %s", sys.version.split()[0], sys.platform)
    logger.info("Dependencies: %s", _dep_summary())
    logger.info(
        "Run mode: %s | log level: %s | log format: %s",
        run_mode,
        log_level,
        log_format,
    )
    for handler in logging.root.handlers:
        handler.flush()

    return logger


def _dep_summary() -> str:
    """Comma-separated 'pkg=version' string for the three runtime deps that
    matter for triage. Missing packages report '?'."""
    from importlib.metadata import PackageNotFoundError, version

    pkgs = ("aanalytics2", "pandas", "xlsxwriter")
    parts: list[str] = []
    for p in pkgs:
        try:
            parts.append(f"{p}={version(p)}")
        except PackageNotFoundError:
            parts.append(f"{p}=?")
    return ", ".join(parts)
