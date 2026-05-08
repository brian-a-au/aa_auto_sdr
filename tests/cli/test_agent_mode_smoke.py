"""End-to-end agent-mode smoke tests (mocked SDK). Spec §7."""

from __future__ import annotations

import json
import logging

import pytest


@pytest.fixture(autouse=True)
def _teardown_logging():
    yield
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)


def test_diff_under_agent_mode_emits_json_to_stdout(tmp_path, monkeypatch, capsys):
    """`--diff <a> <b> --agent-mode` emits DiffReport JSON on stdout."""
    monkeypatch.chdir(tmp_path)

    # Prepare two minimal snapshot files (must match aa-sdr-snapshot/v1 schema)
    snap_a = tmp_path / "a.json"
    snap_b = tmp_path / "b.json"
    base_payload = {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": "RS1",
        "captured_at": "2026-05-07T00:00:00Z",
        "tool_version": "1.6.0",
        "components": {
            "report_suite": {
                "rsid": "RS1",
                "name": "RS1",
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
    snap_a.write_text(json.dumps(base_payload))
    snap_b.write_text(json.dumps({**base_payload, "captured_at": "2026-05-07T01:00:00Z"}))

    from aa_auto_sdr.cli.main import run

    exit_code = run(["--diff", str(snap_a), str(snap_b), "--agent-mode"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert "components" in payload  # DiffReport JSON shape


def test_list_reportsuites_under_agent_mode_emits_json(monkeypatch, capsys, tmp_path):
    """`--list-reportsuites --agent-mode` emits a JSON array on stdout."""
    monkeypatch.chdir(tmp_path)
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.models import ReportSuiteSummary
    from aa_auto_sdr.core import credentials
    from aa_auto_sdr.core.credentials import Credentials

    monkeypatch.setattr(
        credentials,
        "resolve",
        lambda profile=None: Credentials(  # noqa: ARG005
            org_id="x",
            client_id="y",
            secret="z",
            scopes="openid,AdobeID,additional_info.projectedProductContext",
            source="test",
        ),
    )
    monkeypatch.setattr(
        AaClient,
        "from_credentials",
        classmethod(lambda cls, creds: object()),  # noqa: ARG005
    )
    monkeypatch.setattr(
        fetch,
        "fetch_report_suite_summaries",
        lambda client: [  # noqa: ARG005
            ReportSuiteSummary(rsid="RS1", name="Suite 1"),
            ReportSuiteSummary(rsid="RS2", name="Suite 2"),
        ],
    )

    from aa_auto_sdr.cli.main import run

    exit_code = run(["--list-reportsuites", "--agent-mode"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert isinstance(payload, list)
    assert any(row["rsid"] == "RS1" for row in payload)


def test_list_metrics_under_agent_mode_emits_json(monkeypatch, capsys, tmp_path):
    """`--list-metrics RS1 --agent-mode` emits JSON array on stdout."""
    monkeypatch.chdir(tmp_path)
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.models import Metric
    from aa_auto_sdr.core import credentials
    from aa_auto_sdr.core.credentials import Credentials

    monkeypatch.setattr(
        credentials,
        "resolve",
        lambda profile=None: Credentials(  # noqa: ARG005
            org_id="x",
            client_id="y",
            secret="z",
            scopes="openid,AdobeID,additional_info.projectedProductContext",
            source="test",
        ),
    )
    monkeypatch.setattr(AaClient, "from_credentials", classmethod(lambda cls, creds: object()))  # noqa: ARG005
    monkeypatch.setattr(fetch, "resolve_rsid", lambda client, ident: (["RS1"], False))  # noqa: ARG005
    monkeypatch.setattr(
        fetch,
        "fetch_metrics",
        lambda client, rsid: [  # noqa: ARG005
            Metric(
                id="m1",
                name="Metric 1",
                type="counter",
                category="Standard",
                precision=0,
                segmentable=True,
                description="",
            )
        ],
    )

    from aa_auto_sdr.cli.main import run

    exit_code = run(["--list-metrics", "RS1", "--agent-mode"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert isinstance(payload, list)
    assert payload[0]["id"] == "m1"


def test_single_sdr_under_agent_mode_writes_file_not_stdout(monkeypatch, tmp_path, capsys):
    """`<RSID> --agent-mode` writes auto-named artifact under cwd; agent-mode `--output -` is suppressed."""
    monkeypatch.chdir(tmp_path)
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.models import ReportSuite
    from aa_auto_sdr.core import credentials
    from aa_auto_sdr.core.credentials import Credentials

    monkeypatch.setattr(
        credentials,
        "resolve",
        lambda profile=None: Credentials(  # noqa: ARG005
            org_id="x",
            client_id="y",
            secret="z",
            scopes="openid,AdobeID,additional_info.projectedProductContext",
            source="test",
        ),
    )
    monkeypatch.setattr(AaClient, "from_credentials", classmethod(lambda cls, creds: object()))  # noqa: ARG005
    monkeypatch.setattr(fetch, "resolve_rsid", lambda client, ident: (["RS1"], False))  # noqa: ARG005
    monkeypatch.setattr(
        fetch,
        "fetch_report_suite",
        lambda client, rsid: ReportSuite(rsid="RS1", name="Suite", timezone="UTC", currency="USD", parent_rsid=None),  # noqa: ARG005
    )
    monkeypatch.setattr(fetch, "fetch_dimensions", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_metrics", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_segments", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_calculated_metrics", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_virtual_report_suites", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_classification_datasets", lambda c, r: [])  # noqa: ARG005

    from aa_auto_sdr.cli.main import run

    exit_code = run(["RS1", "--agent-mode", "--format", "json"])
    capsys.readouterr()  # consume any stdout

    # Output goes to a file under cwd, not stdout. Don't be too prescriptive on filename.
    assert exit_code == 0
    json_files = list(tmp_path.glob("**/*.json")) + list(tmp_path.glob("**/*RS1*"))
    # Filter to just files (not dirs), and ignore log files
    written = [
        p
        for p in json_files
        if p.is_file() and p.suffix == ".json" and "logs" not in p.parts and p.name not in ("a.json", "b.json")
    ]
    assert written, f"expected an SDR JSON artifact under {tmp_path}, got {list(tmp_path.iterdir())}"


def test_describe_reportsuite_under_agent_mode_emits_json(monkeypatch, capsys, tmp_path):
    """Round-3 smoke: `--describe-reportsuite RS1 --agent-mode` emits JSON on stdout.

    Covers the 6th inspect dispatch site, which the v1.6 wiring routes through
    the same resolver as the five `--list-X` actions.
    """
    monkeypatch.chdir(tmp_path)
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.models import ReportSuite
    from aa_auto_sdr.core import credentials
    from aa_auto_sdr.core.credentials import Credentials

    monkeypatch.setattr(
        credentials,
        "resolve",
        lambda profile=None: Credentials(  # noqa: ARG005
            org_id="x",
            client_id="y",
            secret="z",
            scopes="openid,AdobeID,additional_info.projectedProductContext",
            source="test",
        ),
    )
    monkeypatch.setattr(AaClient, "from_credentials", classmethod(lambda cls, creds: object()))  # noqa: ARG005
    monkeypatch.setattr(fetch, "resolve_rsid", lambda client, ident: (["RS1"], False))  # noqa: ARG005
    monkeypatch.setattr(
        fetch,
        "fetch_report_suite",
        lambda client, rsid: ReportSuite(rsid="RS1", name="Suite 1", timezone="UTC", currency="USD", parent_rsid=None),  # noqa: ARG005
    )
    monkeypatch.setattr(fetch, "fetch_dimensions", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_metrics", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_segments", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_calculated_metrics", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_virtual_report_suites", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_classification_datasets", lambda c, r: [])  # noqa: ARG005

    from aa_auto_sdr.cli.main import run

    exit_code = run(["--describe-reportsuite", "RS1", "--agent-mode"])
    captured = capsys.readouterr()

    assert exit_code == 0
    # Confirm the output is parseable JSON and the RSID is in the payload.
    json.loads(captured.out)  # raises if not valid JSON
    assert "RS1" in captured.out


def test_batch_under_agent_mode_writes_files_per_rsid(monkeypatch, tmp_path, capsys):
    """Round-3 smoke: `RS1 RS2 --agent-mode` writes one artifact set per RSID to cwd.

    Exercises the batch dispatch resolver wiring (Option A: `stdout_formats=frozenset()`),
    which suppresses the agent-mode implicit `--output -` so the existing batch error
    (`--output - is ambiguous for batch runs`) does not spuriously fire.
    """
    monkeypatch.chdir(tmp_path)
    from aa_auto_sdr.api import fetch
    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.models import ReportSuite
    from aa_auto_sdr.core import credentials
    from aa_auto_sdr.core.credentials import Credentials

    monkeypatch.setattr(
        credentials,
        "resolve",
        lambda profile=None: Credentials(  # noqa: ARG005
            org_id="x",
            client_id="y",
            secret="z",
            scopes="openid,AdobeID,additional_info.projectedProductContext",
            source="test",
        ),
    )
    monkeypatch.setattr(AaClient, "from_credentials", classmethod(lambda cls, creds: object()))  # noqa: ARG005
    monkeypatch.setattr(fetch, "resolve_rsid", lambda client, ident: ([ident], False))  # noqa: ARG005
    monkeypatch.setattr(
        fetch,
        "fetch_report_suite",
        lambda client, rsid: ReportSuite(
            rsid=rsid, name=f"Suite {rsid}", timezone="UTC", currency="USD", parent_rsid=None
        ),  # noqa: ARG005
    )
    monkeypatch.setattr(fetch, "fetch_dimensions", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_metrics", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_segments", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_calculated_metrics", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_virtual_report_suites", lambda c, r: [])  # noqa: ARG005
    monkeypatch.setattr(fetch, "fetch_classification_datasets", lambda c, r: [])  # noqa: ARG005

    from aa_auto_sdr.cli.main import run

    exit_code = run(["RS1", "RS2", "--agent-mode", "--format", "json"])
    capsys.readouterr()  # consume any stdout

    assert exit_code == 0
    written = [
        p for p in tmp_path.glob("**/*.json") if p.is_file() and "logs" not in p.parts and "snapshots" not in p.parts
    ]
    rsids_in_filenames = {rsid for rsid in ("RS1", "RS2") if any(rsid in p.name for p in written)}
    assert rsids_in_filenames == {"RS1", "RS2"}, (
        f"expected SDR artifacts for both RS1 and RS2, got files: {[p.name for p in written]}"
    )
