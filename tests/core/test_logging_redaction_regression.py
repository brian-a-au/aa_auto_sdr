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
        for h in logging.root.handlers:
            h.flush()
        log_file = next((tmp_path / "logs").glob("SDR_Generation_abc_*.log"))
        text = log_file.read_text(encoding="utf-8")
        assert FAKE_TOKEN not in text, "bearer token leaked past v1.3 redaction"
        assert "[REDACTED]" in text, "redaction sentinel not present"
    finally:
        # Teardown: close and remove handlers since we don't have the autouse fixture.
        for h in logging.root.handlers[:]:
            h.close()
            logging.root.removeHandler(h)
