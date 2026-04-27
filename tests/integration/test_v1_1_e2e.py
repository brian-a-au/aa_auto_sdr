"""End-to-end test of the three v1.1 subsystems against fixture data.

Exercises:
- profile-import: write a credentials profile from a JSON file.
- snapshot lifecycle: list snapshots, then prune by retention policy.
- diff: compare @latest vs @previous snapshots in pr-comment format.

Hermetic — no real Adobe API calls. Synthetic envelopes are dropped directly
into the snapshot dir to simulate prior auto-snapshot saves."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _fixture_envelope(rsid: str, captured_at: str, *, metric_name: str) -> dict:
    return {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": rsid,
        "captured_at": captured_at,
        "tool_version": "1.1.0",
        "components": {
            "report_suite": {
                "rsid": rsid,
                "name": rsid,
                "timezone": "UTC",
                "currency": "USD",
                "parent_rsid": None,
            },
            "dimensions": [],
            "metrics": [{"id": "m1", "name": metric_name}],
            "segments": [],
            "calculated_metrics": [],
            "virtual_report_suites": [],
            "classifications": [],
        },
    }


def test_v1_1_full_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """profile-import → list-snapshots → diff @latest @previous → prune --keep-last 1."""
    monkeypatch.setenv("HOME", str(tmp_path))

    # 1. Import a credentials profile.
    from aa_auto_sdr.cli.commands.profiles import import_run

    creds_src = tmp_path / "creds.json"
    creds_src.write_text(
        json.dumps(
            {
                "org_id": "x@AdobeOrg",
                "client_id": "abcdefgh12345678",
                "secret": "topsecret",
                "scopes": "openid",
            },
        ),
    )
    rc = import_run("e2e", str(creds_src))
    assert rc == 0
    assert (tmp_path / ".aa" / "orgs" / "e2e" / "config.json").exists()

    # 2. Drop two synthetic envelopes directly into the snapshot dir
    #    (simulates two prior --auto-snapshot saves on different days).
    snap_dir = tmp_path / ".aa" / "orgs" / "e2e" / "snapshots" / "RS1"
    snap_dir.mkdir(parents=True)
    env_a = _fixture_envelope("RS1", "2026-04-25T10:00:00+00:00", metric_name="Old")
    env_b = _fixture_envelope("RS1", "2026-04-26T10:00:00+00:00", metric_name="New")
    (snap_dir / "2026-04-25T10-00-00+00-00.json").write_text(json.dumps(env_a))
    (snap_dir / "2026-04-26T10-00-00+00-00.json").write_text(json.dumps(env_b))

    # 3. List snapshots — JSON format, two entries.
    from aa_auto_sdr.cli.commands.snapshots import list_run, prune_run

    rc = list_run(profile="e2e", rsid=None, format_name="json")
    assert rc == 0

    # 4. Diff @latest @previous as pr-comment.
    from aa_auto_sdr.cli.commands.diff import run as diff_run

    rc = diff_run(
        a="RS1@previous",
        b="RS1@latest",
        format_name="pr-comment",
        output=None,
        profile="e2e",
        side_by_side=False,
        summary=False,
        ignore_fields=frozenset(),
    )
    assert rc == 0

    # 5. Prune to keep last 1.
    rc = prune_run(
        profile="e2e",
        rsid=None,
        keep_last=1,
        keep_since=None,
        dry_run=False,
        assume_yes=True,  # v1.2: confirmation gate
    )
    assert rc == 0
    surviving = list(snap_dir.glob("*.json"))
    assert len(surviving) == 1


def test_v1_1_diff_with_ignore_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Diff with ignore_fields filters out the changed field entirely."""
    monkeypatch.setenv("HOME", str(tmp_path))

    from aa_auto_sdr.cli.commands.profiles import import_run

    creds_src = tmp_path / "creds.json"
    creds_src.write_text(
        json.dumps(
            {
                "org_id": "x@AdobeOrg",
                "client_id": "abcdefgh12345678",
                "secret": "topsecret",
                "scopes": "openid",
            },
        ),
    )
    import_run("e2e", str(creds_src))

    snap_dir = tmp_path / ".aa" / "orgs" / "e2e" / "snapshots" / "RS1"
    snap_dir.mkdir(parents=True)
    env_a = {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": "RS1",
        "captured_at": "2026-04-25T10:00:00+00:00",
        "tool_version": "1.1.0",
        "components": {
            "report_suite": {
                "rsid": "RS1",
                "name": "RS1",
                "timezone": "UTC",
                "currency": "USD",
                "parent_rsid": None,
            },
            "dimensions": [],
            "metrics": [{"id": "m1", "name": "M", "description": "old desc"}],
            "segments": [],
            "calculated_metrics": [],
            "virtual_report_suites": [],
            "classifications": [],
        },
    }
    env_b = {
        **env_a,
        "captured_at": "2026-04-26T10:00:00+00:00",
        "components": {
            **env_a["components"],
            "metrics": [{"id": "m1", "name": "M", "description": "new desc"}],
        },
    }
    (snap_dir / "2026-04-25T10-00-00+00-00.json").write_text(json.dumps(env_a))
    (snap_dir / "2026-04-26T10-00-00+00-00.json").write_text(json.dumps(env_b))

    # Diff with ignore_fields={"description"} — the only changed field.
    # Result should report no modifications.
    from aa_auto_sdr.cli.commands.diff import run as diff_run

    diff_out = tmp_path / "diff.json"
    rc = diff_run(
        a="RS1@previous",
        b="RS1@latest",
        format_name="json",
        output=str(diff_out),
        profile="e2e",
        side_by_side=False,
        summary=False,
        ignore_fields=frozenset({"description"}),
    )
    assert rc == 0
    payload = json.loads(diff_out.read_text())
    metric_block = next(c for c in payload["components"] if c["component_type"] == "metrics")
    assert metric_block["modified"] == []
