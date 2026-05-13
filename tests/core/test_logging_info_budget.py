"""v1.5 — assert default-INFO line counts at single / batch / diff are within
the spec §8.8 budgets. Counts are read from the per-run log file (not caplog)
so the assertion includes the 5-record startup banner.

Pattern A from the autouse-fixture disambiguation table:
- ``setup_logging`` fires (via ``cli.main.run``), so we attach
  ``caplog.handler`` to the package logger to survive the root-handler reset
  done inside setup_logging — even though this test reads the on-disk file
  rather than ``caplog.records``, the autouse fixture keeps the package
  logger sane between tests.
- ``_isolate_root_handlers`` snapshots and restores the root logger so the
  per-run RotatingFileHandler from one test doesn't leak file handles into
  the next test in this module.
"""

from __future__ import annotations

import json
import logging
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.main import run


@pytest.fixture(autouse=True)
def _attach_caplog_to_package_logger(caplog):
    """Attach caplog's handler to the aa_auto_sdr package logger so records
    survive setup_logging's root-handler reset, then restore on teardown so
    handlers don't leak into other tests."""
    pkg = logging.getLogger("aa_auto_sdr")
    saved_handlers = pkg.handlers[:]
    saved_level = pkg.level
    pkg.addHandler(caplog.handler)
    pkg.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        pkg.handlers.clear()
        for h in saved_handlers:
            pkg.addHandler(h)
        pkg.setLevel(saved_level)


@pytest.fixture(autouse=True)
def _isolate_root_handlers():
    """Snapshot the root logger handler list before each test, restore after.
    Prevents the per-run RotatingFileHandler installed by setup_logging from
    leaking across tests in this module."""
    root = logging.getLogger()
    saved = root.handlers[:]
    saved_level = root.level
    yield
    for h in root.handlers[:]:
        h.close()
        root.removeHandler(h)
    for h in saved:
        root.addHandler(h)
    root.setLevel(saved_level)


def _read_log_file(tmp_path: Path) -> list[str]:
    log_files = sorted((tmp_path / "logs").glob("*.log"))
    assert log_files, f"expected a log file under {tmp_path / 'logs'}"
    return [line for line in log_files[-1].read_text().splitlines() if line.strip()]


def _empty_fetcher_patches() -> list:
    """Patch the high-level non-component fetchers — ``fetch_report_suite``
    and ``resolve_rsid`` — so the test doesn't depend on a real
    ``client.handle.getReportSuites`` shape.

    Per-component fetchers (``fetch_dimensions`` / ``fetch_metrics`` / etc.)
    are deliberately NOT patched here: they emit the ``component_fetch``
    INFO records the budget asserts. With ``aanalytics2.Analytics`` mocked,
    those fetchers see a ``MagicMock`` from ``client.handle.get*(...)`` which
    ``_records`` coerces to an empty list — so each component fetcher runs
    end-to-end (including its INFO log) but returns no components.
    """
    return []


def _set_env(monkeypatch):
    monkeypatch.setenv("ORG_ID", "id@AdobeOrg")
    monkeypatch.setenv("CLIENT_ID", "ci")
    monkeypatch.setenv("SECRET", "s")
    monkeypatch.setenv("SCOPES", "openid,AdobeID,additional_info.projectedProductContext")


def _make_report_suite_mock(rsid: str = "RS1"):
    """Build a mock ReportSuite-shaped object whose attributes the SDR
    builder reads (rsid, name, timezone, currency, parent_rsid)."""
    rs = MagicMock()
    rs.rsid = rsid
    rs.name = "Test RS"
    rs.timezone = None
    rs.currency = None
    rs.parent_rsid = None
    return rs


def test_single_rsid_excel_info_budget(tmp_path, monkeypatch):
    """Spec §8.1: single-RSID --format excel = 19 lines ±2 → 17..21."""
    monkeypatch.chdir(tmp_path)
    _set_env(monkeypatch)

    fetcher_patches = _empty_fetcher_patches()
    with ExitStack() as stack:
        for p in fetcher_patches:
            stack.enter_context(p)
        stack.enter_context(patch("aa_auto_sdr.api.client.aanalytics2.configure"))
        login = stack.enter_context(patch("aa_auto_sdr.api.client.aanalytics2.Login"))
        stack.enter_context(patch("aa_auto_sdr.api.client.aanalytics2.Analytics"))
        rs_patch = stack.enter_context(patch("aa_auto_sdr.api.fetch.fetch_report_suite"))
        stack.enter_context(
            patch("aa_auto_sdr.api.fetch.resolve_rsid", return_value=(["RS1"], False)),
        )

        login.return_value.getCompanyId.return_value = [{"globalCompanyId": "co"}]
        rs_patch.return_value = _make_report_suite_mock("RS1")

        exit_code = run(
            [
                "RS1",
                "--format",
                "excel",
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )

    assert exit_code == 0, f"unexpected exit code {exit_code}"
    lines = _read_log_file(tmp_path)
    assert 17 <= len(lines) <= 21, f"expected 17..21 lines (spec §8.1: 19 ±2); got {len(lines)}: {lines!r}"


def test_batch_n2_excel_info_budget(tmp_path, monkeypatch):
    """Spec §8.3: batch N=2 --format excel = 12 + 9·2 = 30 lines ±2 → 28..32."""
    monkeypatch.chdir(tmp_path)
    _set_env(monkeypatch)

    fetcher_patches = _empty_fetcher_patches()
    with ExitStack() as stack:
        for p in fetcher_patches:
            stack.enter_context(p)
        stack.enter_context(patch("aa_auto_sdr.api.client.aanalytics2.configure"))
        login = stack.enter_context(patch("aa_auto_sdr.api.client.aanalytics2.Login"))
        stack.enter_context(patch("aa_auto_sdr.api.client.aanalytics2.Analytics"))
        rs_patch = stack.enter_context(patch("aa_auto_sdr.api.fetch.fetch_report_suite"))
        # resolve_rsid maps each input identifier to itself, no name lookup.
        stack.enter_context(
            patch(
                "aa_auto_sdr.api.fetch.resolve_rsid",
                side_effect=lambda _client, ident, **_kwargs: ([ident], False),
            ),
        )

        login.return_value.getCompanyId.return_value = [{"globalCompanyId": "co"}]
        rs_patch.side_effect = lambda _client, rsid: _make_report_suite_mock(rsid)

        exit_code = run(
            [
                "RS1",
                "RS2",
                "--format",
                "excel",
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )

    assert exit_code == 0, f"unexpected exit code {exit_code}"
    lines = _read_log_file(tmp_path)
    assert 28 <= len(lines) <= 32, f"expected 28..32 lines (spec §8.3: 30 ±2); got {len(lines)}: {lines!r}"


def test_info_budget_unchanged_on_vrs_degrade(tmp_path, monkeypatch, caplog):
    """v1.7.0 — VRS-degraded run hits the SAME INFO count as a healthy run.

    The full-expansion rung fast-fails on ``KeyError("content")``
    (v1.16.1: classified as permanent VrsEndpointShapeError — no retries);
    the minimal-expansion rung succeeds. The degradation surfaces at WARNING
    (``vrs_expansion_fallback``), NEVER at INFO — so the INFO budget is
    unchanged from the healthy single-RSID excel run (spec §8.1: 19 ±2).
    A future change that promotes a DEBUG/WARNING record on this path to
    INFO would silently inflate the budget; this test locks that down.
    """
    monkeypatch.chdir(tmp_path)
    _set_env(monkeypatch)
    monkeypatch.setattr("aa_auto_sdr.api.resilience.time.sleep", lambda _s: None)

    fetcher_patches = _empty_fetcher_patches()
    with ExitStack() as stack:
        for p in fetcher_patches:
            stack.enter_context(p)
        stack.enter_context(patch("aa_auto_sdr.api.client.aanalytics2.configure"))
        login = stack.enter_context(patch("aa_auto_sdr.api.client.aanalytics2.Login"))
        analytics = stack.enter_context(patch("aa_auto_sdr.api.client.aanalytics2.Analytics"))
        rs_patch = stack.enter_context(patch("aa_auto_sdr.api.fetch.fetch_report_suite"))
        stack.enter_context(
            patch("aa_auto_sdr.api.fetch.resolve_rsid", return_value=(["RS1"], False)),
        )

        login.return_value.getCompanyId.return_value = [{"globalCompanyId": "co"}]
        rs_patch.return_value = _make_report_suite_mock("RS1")

        # Drive the VRS ladder: full-expansion rung (extended_info=True)
        # fast-fails on KeyError("content") — v1.16.1 classifies this as
        # permanent VrsEndpointShapeError, no retries — then the minimal-
        # expansion rung (extended_info=False) succeeds on its first try.
        # Total SDK calls: 1 (full, fast-fail) + 1 (minimal) = 2.
        handle = analytics.return_value
        handle.getVirtualReportSuites.side_effect = [
            KeyError("content"),  # full rung — permanent, fast-fail
            [],  # minimal rung — success (empty list)
        ]

        caplog.set_level(logging.DEBUG)
        exit_code = run(
            [
                "RS1",
                "--format",
                "excel",
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )

    assert exit_code == 0, f"unexpected exit code {exit_code}"

    info_records = [r for r in caplog.records if r.levelname == "INFO"]
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]

    # 19 ±2 — same envelope as the healthy single-RSID excel scenario.
    # Locks down the spec §8.1 budget against accidental DEBUG→INFO promotions
    # on the VRS-degraded path.
    assert 17 <= len(info_records) <= 21, (
        f"expected 17..21 INFO records (spec §8.1: 19 ±2); "
        f"got {len(info_records)}: {[r.message for r in info_records]!r}"
    )
    # Exactly one WARNING — the vrs_expansion_fallback record. The
    # vrs_unavailable additive WARNING only fires when BOTH rungs exhaust;
    # here the minimal rung succeeds so only vrs_expansion_fallback fires.
    assert len(warning_records) == 1, (
        f"expected exactly 1 WARNING (vrs_expansion_fallback); "
        f"got {len(warning_records)}: {[r.message for r in warning_records]!r}"
    )
    msg = warning_records[0].getMessage()
    assert "vrs_expansion_fallback" in msg, msg
    assert "minimal" in msg, msg
    # Belt-and-suspenders: confirm the SDK was actually called the expected
    # number of times — 1 fast-fail on the full rung + 1 successful call on
    # the minimal rung = 2 total. If aanalytics2 gets called fewer times,
    # the side_effect didn't drive both rungs and the test isn't proving what
    # it claims to prove.
    assert handle.getVirtualReportSuites.call_count == 2, (
        f"expected 2 SDK calls (1 full-rung fast-fail + 1 minimal-rung success); "
        f"got {handle.getVirtualReportSuites.call_count}"
    )


def test_diff_info_budget(tmp_path, monkeypatch):
    """Spec §8.5: diff = 9 lines ±2 → 7..11.

    No auth, no per-component fetches: diff operates on snapshot files.
    Snapshot resolution and comparator work happen at DEBUG; INFO budget
    is purely banner + run_start + command_start + command_complete +
    run_complete.
    """
    monkeypatch.chdir(tmp_path)
    snap_dir = tmp_path / "snaps"
    snap_dir.mkdir()
    # Canonical v1 envelope shape per src/aa_auto_sdr/snapshot/schema.py:
    # `report_suite` lives under `components`, not at the top level.
    envelope = {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": "RS1",
        "captured_at": "2026-04-29T00:00:00+00:00",
        "tool_version": "1.5.0",
        "components": {
            "report_suite": {
                "rsid": "RS1",
                "name": "n",
                "timezone": "UTC",
                "currency": "USD",
                "parent_rsid": None,
            },
            "dimensions": [],
            "metrics": [],
            "segments": [],
            "calculated_metrics": [],
            "virtual_report_suites": [],
            "classifications": [],
        },
    }
    a_path = snap_dir / "a.json"
    b_path = snap_dir / "b.json"
    a_path.write_text(json.dumps(envelope))
    # Slight diff so the report has at least one component change to render.
    envelope_b = {
        **envelope,
        "components": {
            **envelope["components"],
            "report_suite": {**envelope["components"]["report_suite"], "name": "n2"},
        },
    }
    b_path.write_text(json.dumps(envelope_b))

    exit_code = run(
        [
            "--diff",
            str(a_path),
            str(b_path),
            "--format",
            "json",
            "--output",
            "-",
        ]
    )
    # Diff exit code is 0 (no diff) or 3 (warn threshold tripped). Both fine.
    assert exit_code in (0, 3), f"unexpected exit code {exit_code}"
    lines = _read_log_file(tmp_path)
    assert 7 <= len(lines) <= 11, f"expected 7..11 lines (spec §8.5: 9 ±2); got {len(lines)}: {lines!r}"
