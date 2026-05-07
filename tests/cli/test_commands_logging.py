"""v1.5 — every cli/commands/<module>.py emits command_start /
command_complete INFO records carrying ``command``, ``exit_code``,
``duration_ms`` extras.

Pattern B (per LOGGING_STYLE.md disambiguation table): commands are
invoked directly here without going through ``cli.main.run`` (so
``setup_logging`` is never called); we attach ``caplog`` directly to
each module logger and snapshot/restore the package-logger handlers to
keep the suite hermetic.
"""
# ruff: noqa: ARG005, S110, SIM105
# ARG005: monkeypatched stand-ins use *args/**kwargs lambdas as a tiny
# sentinel — naming each arg with `_` would obscure intent.
# S110/SIM105: the broad try/except/pass is deliberate per the plan; some
# entries raise on missing fixtures (input(), missing files) and the
# point of the test is purely to assert lifecycle records fired.

from __future__ import annotations

import importlib
import logging
from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.core.credentials import Credentials


@pytest.fixture(autouse=True)
def _isolate_package_logger():
    """Snapshot/restore handlers on the ``aa_auto_sdr`` package logger so
    leaks from sibling tests (e.g. cli.main_logging) don't double-capture
    propagating records here."""
    pkg = logging.getLogger("aa_auto_sdr")
    saved_handlers = pkg.handlers[:]
    saved_level = pkg.level
    pkg.handlers.clear()
    try:
        yield
    finally:
        pkg.handlers.clear()
        for h in saved_handlers:
            pkg.addHandler(h)
        pkg.setLevel(saved_level)


@pytest.fixture
def auth_mocks(monkeypatch):
    """Patch ``credentials.resolve`` + ``AaClient.from_credentials`` + the
    SDK fetchers commands use, so any auth-needing command path completes
    deterministically without round-tripping Adobe."""
    fake_creds = Credentials(
        org_id="11112222@AdobeOrg",
        client_id="abcdef1234567890",
        secret="secret-shh",
        scopes="openid,AdobeID,additional_info.projectedProductContext",
        source="env",
    )
    monkeypatch.setattr(
        "aa_auto_sdr.core.credentials.resolve",
        lambda **kw: fake_creds,
    )
    fake_handle = MagicMock()
    fake_client = MagicMock(handle=fake_handle, company_id="co42")
    monkeypatch.setattr(
        "aa_auto_sdr.api.client.AaClient.from_credentials",
        classmethod(lambda cls, *a, **kw: fake_client),
    )

    # Broadly patch fetchers so any auth-needing path returns empty/safe
    # values rather than calling the SDK.
    monkeypatch.setattr(
        "aa_auto_sdr.api.fetch.resolve_rsid",
        lambda client, ident: ([ident], False),
    )
    monkeypatch.setattr(
        "aa_auto_sdr.api.fetch.fetch_report_suite_summaries",
        lambda client: [],
    )
    monkeypatch.setattr(
        "aa_auto_sdr.api.fetch.fetch_virtual_report_suite_summaries",
        lambda client: [],
    )
    monkeypatch.setattr("aa_auto_sdr.api.fetch.fetch_metrics", lambda client, rsid: [])
    monkeypatch.setattr("aa_auto_sdr.api.fetch.fetch_dimensions", lambda client, rsid: [])
    monkeypatch.setattr("aa_auto_sdr.api.fetch.fetch_segments", lambda client, rsid: [])
    monkeypatch.setattr(
        "aa_auto_sdr.api.fetch.fetch_calculated_metrics",
        lambda client, rsid: [],
    )
    monkeypatch.setattr(
        "aa_auto_sdr.api.fetch.fetch_classification_datasets",
        lambda client, rsid: [],
    )
    monkeypatch.setattr(
        "aa_auto_sdr.api.fetch.fetch_virtual_report_suites",
        lambda client, rsid: [],
    )

    # fetch_report_suite returns a normalized model; safest is to patch it
    # to raise NotFound so describe/stats short-circuit cleanly. The
    # parametrized test wraps the call in a broad except so this is fine.
    from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError

    def _missing(client, rsid):
        raise ReportSuiteNotFoundError(f"rsid '{rsid}' not visible")

    monkeypatch.setattr("aa_auto_sdr.api.fetch.fetch_report_suite", _missing)

    return fake_handle


# 24 rows: (module, fn_name, call_args, expected_command, needs_auth)
_PARAMS = [
    # --- config.py: 5 entries, none need auth ---
    (
        "aa_auto_sdr.cli.commands.config",
        "profile_add",
        {"name": "newprof"},
        "profile_add",
        False,
    ),
    (
        "aa_auto_sdr.cli.commands.config",
        "show_config",
        {"profile": None},
        "show_config",
        False,
    ),
    (
        "aa_auto_sdr.cli.commands.config",
        "config_status",
        {"profile": None},
        "config_status",
        False,
    ),
    (
        "aa_auto_sdr.cli.commands.config",
        "validate_config",
        {"profile": None},
        "validate_config",
        False,
    ),
    (
        "aa_auto_sdr.cli.commands.config",
        "sample_config",
        {},
        "sample_config",
        False,
    ),
    # --- profiles.py: 4 entries; only test_run hits Adobe ---
    (
        "aa_auto_sdr.cli.commands.profiles",
        "list_run",
        {"format_name": None},
        "profile_list",
        False,
    ),
    (
        "aa_auto_sdr.cli.commands.profiles",
        "show_run",
        {"name": "x"},
        "profile_show",
        False,
    ),
    (
        "aa_auto_sdr.cli.commands.profiles",
        "import_run",
        {"name": "x", "file_path": "x", "overwrite": False},
        "profile_import",
        False,
    ),
    (
        "aa_auto_sdr.cli.commands.profiles",
        "test_run",
        {"name": "x"},
        "profile_test",
        True,
    ),
    # --- snapshots.py: 2 entries, no auth ---
    (
        "aa_auto_sdr.cli.commands.snapshots",
        "list_run",
        {"profile": None, "rsid": None, "format_name": None},
        "list_snapshots",
        False,
    ),
    (
        "aa_auto_sdr.cli.commands.snapshots",
        "prune_run",
        {
            "profile": None,
            "rsid": None,
            "keep_last": 0,
            "keep_since": None,
            "dry_run": True,
            "assume_yes": True,
        },
        "prune_snapshots",
        False,
    ),
    # --- diff.py: snapshot files, no auth ---
    (
        "aa_auto_sdr.cli.commands.diff",
        "run",
        {
            "a": "fixture-a",
            "b": "fixture-b",
            "format_name": "json",
            "output": "-",
            "profile": None,
        },
        "diff",
        False,
    ),
    # --- generate / batch / discovery / inspect / stats / interactive: auth ---
    (
        "aa_auto_sdr.cli.commands.stats",
        "run",
        {"rsids": [], "profile": None, "format_name": None},
        "stats",
        True,
    ),
    (
        "aa_auto_sdr.cli.commands.interactive",
        "run",
        {"profile": None},
        "interactive",
        True,
    ),
    (
        "aa_auto_sdr.cli.commands.discovery",
        "run_list_reportsuites",
        {
            "profile": None,
            "format_name": None,
            "output": "-",
            "name_filter": None,
            "name_exclude": None,
            "sort_field": None,
            "limit": None,
        },
        "list_reportsuites",
        True,
    ),
    (
        "aa_auto_sdr.cli.commands.discovery",
        "run_list_virtual_reportsuites",
        {
            "profile": None,
            "format_name": None,
            "output": "-",
            "name_filter": None,
            "name_exclude": None,
            "sort_field": None,
            "limit": None,
        },
        "list_virtual_reportsuites",
        True,
    ),
    (
        "aa_auto_sdr.cli.commands.inspect",
        "run_describe_reportsuite",
        {
            "identifier": "rs1",
            "profile": None,
            "format_name": None,
            "output": "-",
        },
        "describe_reportsuite",
        True,
    ),
    (
        "aa_auto_sdr.cli.commands.inspect",
        "run_list_metrics",
        {
            "identifier": "rs1",
            "profile": None,
            "format_name": None,
            "output": "-",
            "name_filter": None,
            "name_exclude": None,
            "sort_field": None,
            "limit": None,
        },
        "list_metrics",
        True,
    ),
    (
        "aa_auto_sdr.cli.commands.inspect",
        "run_list_dimensions",
        {
            "identifier": "rs1",
            "profile": None,
            "format_name": None,
            "output": "-",
            "name_filter": None,
            "name_exclude": None,
            "sort_field": None,
            "limit": None,
        },
        "list_dimensions",
        True,
    ),
    (
        "aa_auto_sdr.cli.commands.inspect",
        "run_list_segments",
        {
            "identifier": "rs1",
            "profile": None,
            "format_name": None,
            "output": "-",
            "name_filter": None,
            "name_exclude": None,
            "sort_field": None,
            "limit": None,
        },
        "list_segments",
        True,
    ),
    (
        "aa_auto_sdr.cli.commands.inspect",
        "run_list_calculated_metrics",
        {
            "identifier": "rs1",
            "profile": None,
            "format_name": None,
            "output": "-",
            "name_filter": None,
            "name_exclude": None,
            "sort_field": None,
            "limit": None,
        },
        "list_calculated_metrics",
        True,
    ),
    (
        "aa_auto_sdr.cli.commands.inspect",
        "run_list_classification_datasets",
        {
            "identifier": "rs1",
            "profile": None,
            "format_name": None,
            "output": "-",
            "name_filter": None,
            "name_exclude": None,
            "sort_field": None,
            "limit": None,
        },
        "list_classification_datasets",
        True,
    ),
    (
        "aa_auto_sdr.cli.commands.generate",
        "run",
        {
            "rsid": "rs1",
            "output_dir": None,  # filled in test body via tmp_path
            "format_name": "json",
            "profile": None,
        },
        "generate",
        True,
    ),
    (
        "aa_auto_sdr.cli.commands.batch",
        "run",
        {
            "rsids": ["rs1"],
            "output_dir": None,  # filled in test body via tmp_path
            "format_name": "excel",
            "profile": None,
        },
        "batch",
        True,
    ),
]


@pytest.mark.parametrize(
    ("module", "fn_name", "call_args", "expected_command", "needs_auth"),
    _PARAMS,
)
def test_command_emits_start_and_complete(
    caplog,
    monkeypatch,
    tmp_path,
    module,
    fn_name,
    call_args,
    expected_command,
    needs_auth,
    request,
):
    if needs_auth:
        request.getfixturevalue("auth_mocks")
    monkeypatch.chdir(tmp_path)

    # Provide tmp_path-based paths for generate/batch which need a real dir.
    args = dict(call_args)
    if "output_dir" in args and args["output_dir"] is None:
        from pathlib import Path

        args["output_dir"] = Path(tmp_path)

    mod = importlib.import_module(module)
    caplog.set_level(logging.INFO, logger=module)
    fn = getattr(mod, fn_name)
    try:
        fn(**args)
    except SystemExit, Exception:
        # Some entry functions may raise on missing fixtures (input(),
        # missing files, etc). Lifecycle records still fire around the call.
        pass

    starts = [r for r in caplog.records if "command_start" in r.getMessage()]
    completes = [r for r in caplog.records if "command_complete" in r.getMessage()]
    assert any(getattr(r, "command", None) == expected_command for r in starts), (
        f"expected command_start for {expected_command!r}; got starts={[getattr(r, 'command', None) for r in starts]}"
    )
    assert any(getattr(r, "command", None) == expected_command for r in completes), (
        f"expected command_complete for {expected_command!r}; "
        f"got completes={[getattr(r, 'command', None) for r in completes]}"
    )
    matched = [r for r in completes if getattr(r, "command", None) == expected_command]
    assert all(isinstance(r.duration_ms, int) for r in matched)
    assert all(isinstance(r.exit_code, int) for r in matched)
