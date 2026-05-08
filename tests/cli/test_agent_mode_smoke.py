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
