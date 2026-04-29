"""Regression guard for v1.4+ call sites that route credentials through logs.

The v1.3 release wired ``SensitiveDataFilter`` onto every handler created by
``setup_logging``. This regression test confirms that a *new* application-layer
log call (the kind a v1.4+ feature might add) still has its Bearer token
scrubbed on disk -- not just the framework's own startup banner.

Without this guard, a future call site that builds a credential-bearing
message string could silently leak past the v1.3 redaction surface.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from aa_auto_sdr.core.logging import setup_logging

FAKE_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9-fake-token-for-test"


def _namespace() -> argparse.Namespace:
    """Hand-rolled Namespace that satisfies every attr ``setup_logging`` and
    ``infer_run_mode`` read today. Mirrors the shim used by the v1.3 redaction
    integration test so the two regression tests stay in lockstep."""
    return argparse.Namespace(
        log_level="INFO",
        log_format="text",
        quiet=False,
        rsids=["abc"],
        batch=[],
        diff=None,
        list_reportsuites=False,
        list_virtual_reportsuites=False,
        describe_reportsuite=None,
        list_metrics=None,
        list_dimensions=None,
        list_segments=None,
        list_calculated_metrics=None,
        list_classification_datasets=None,
        list_snapshots=False,
        prune_snapshots=False,
        profile_add=None,
        profile_test=None,
        profile_show=None,
        profile_list=False,
        profile_import=None,
        show_config=False,
        config_status=False,
        validate_config=False,
        sample_config=False,
        stats=False,
        interactive=False,
    )


def _read_log_file(tmp_path: Path) -> str:
    for h in logging.root.handlers:
        h.flush()
    log_file = next((tmp_path / "logs").glob("SDR_Generation_abc_*.log"))
    return log_file.read_text(encoding="utf-8")


def _teardown_handlers() -> None:
    for h in logging.root.handlers[:]:
        h.close()
        logging.root.removeHandler(h)


def test_bearer_token_in_v14_info_call_is_redacted_on_disk(tmp_path: Path) -> None:
    """Inject a Bearer token through a fresh INFO record after setup_logging
    runs, then read the resulting log file and confirm scrubbing.

    Without this regression guard, a future v1.4+ call site that builds a
    credential-bearing message string could silently leak past v1.3's
    SensitiveDataFilter.
    """
    ns = _namespace()
    setup_logging(ns, log_dir=tmp_path / "logs")
    try:
        logger = logging.getLogger("aa_auto_sdr.test_v14_redaction_regression")
        # Simulate a v1.4+ application call site logging a credential. We use
        # the ``Bearer %s`` shape (token interpolated via logging args) rather
        # than ``Authorization: Bearer %s`` because the v1.3 ``Authorization:``
        # pattern is intentionally greedy through end-of-line and would eat
        # the ``%s`` placeholder before formatting -- a separate edge case
        # already covered by the existing redaction unit suite.
        logger.info("simulated v1.4 call site token=Bearer %s", FAKE_TOKEN)
        text = _read_log_file(tmp_path)
        assert FAKE_TOKEN not in text, "bearer token leaked past v1.3 redaction"
        assert "[REDACTED]" in text, "redaction sentinel not present"
    finally:
        _teardown_handlers()


def test_non_str_msg_is_redacted_on_disk(tmp_path: Path) -> None:
    """Logger calls that pass a non-str msg (e.g. an exception object) must
    still scrub credentials. The v1.4 filter coerces non-str msg to str
    before applying redaction patterns."""
    ns = _namespace()
    setup_logging(ns, log_dir=tmp_path / "logs")
    try:
        logger = logging.getLogger("aa_auto_sdr.test_v14_nonstr_msg")
        # Build an exception whose str() carries a Bearer token, then pass
        # it as msg directly (not via exc_info). This exercises the non-str
        # msg branch of the filter.
        exc = RuntimeError(f"upstream rejected token=Bearer {FAKE_TOKEN}")
        logger.error(exc)
        text = _read_log_file(tmp_path)
        assert FAKE_TOKEN not in text, "non-str msg leaked credential past redaction"
        assert "[REDACTED]" in text, "redaction sentinel not present"
    finally:
        _teardown_handlers()


def test_exc_info_traceback_is_redacted_on_disk(tmp_path: Path) -> None:
    """``logger.exception(...)`` and ``exc_info=True`` populate
    ``record.exc_info``. The formatter renders the traceback independently
    of ``record.msg``, so the v1.4 filter pre-formats and redacts it,
    storing the result in ``record.exc_text`` and clearing ``exc_info`` to
    prevent re-formatting from leaking the raw traceback."""
    ns = _namespace()
    setup_logging(ns, log_dir=tmp_path / "logs")
    try:
        logger = logging.getLogger("aa_auto_sdr.test_v14_exc_info")
        try:
            raise RuntimeError(f"sdk error: token=Bearer {FAKE_TOKEN}")
        except RuntimeError:
            logger.exception("sdk call failed")
        text = _read_log_file(tmp_path)
        assert FAKE_TOKEN not in text, "traceback leaked credential past redaction"
        assert "[REDACTED]" in text, "redaction sentinel not present in traceback path"
        # The traceback header should still be present so triagers can find it.
        assert "RuntimeError" in text or "Traceback" in text, "traceback structure missing"
    finally:
        _teardown_handlers()
