"""generate command: builds AaClient from credentials, runs single pipeline."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.commands import generate as cmd

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


@pytest.fixture
def env_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


def _build_handle(raw: dict) -> MagicMock:
    import pandas as pd  # local import keeps file linter quiet

    def _df(records: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(records)

    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    return handle


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_writes_excel_default(mock_client_cls, env_creds, tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="excel", profile=None)
    assert rc == 0
    assert (tmp_path / "demo.prod.xlsx").exists()


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_format_data_alias_writes_csv_and_json(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
) -> None:
    """`data` alias = csv + json. Both writers are present in v0.2; this run
    succeeds and produces both output sets (one csv per component + one json)."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="data", profile=None)
    assert rc == 0
    # CSV produces 9 files (no quality audit); JSON produces 1
    csv_files = sorted(p.name for p in tmp_path.glob("demo.prod.*.csv"))
    assert len(csv_files) == 9
    assert (tmp_path / "demo.prod.json").exists()


def test_generate_returns_config_error_when_no_creds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Hermetic test: chdir to tmp_path so credentials.resolve doesn't pick up
    the user's real config.json from the repo root."""
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="excel", profile=None)
    assert rc == 10


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_resolves_unique_name_to_rsid(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    caplog,
) -> None:
    """User passes a unique name; the canonical RSID is logged and used.
    Output filename keyed off canonical RSID, not the input name. v1.5.0
    moved the human-facing 'using report suite: …' line to a structured
    rsid_resolved INFO record (no more stdout)."""
    import logging

    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    caplog.set_level(logging.INFO, logger="aa_auto_sdr.cli.commands.generate")
    # The fixture's report_suite has rsid=demo.prod, name="Demo Production"
    rc = cmd.run(
        rsid="Demo Production",  # name, not rsid
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == 0
    # Output filename is keyed off the canonical RSID
    assert (tmp_path / "demo.prod.json").exists()
    resolved = [r for r in caplog.records if "rsid_resolved" in r.getMessage()]
    assert resolved
    assert any(getattr(r, "rsid", None) == "demo.prod" and "was_name_lookup=True" in r.getMessage() for r in resolved)


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_multi_match_by_name_runs_pipeline_per_rsid(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
    capsys,
) -> None:
    """Two suites share a name. CLI runs the pipeline once per RSID and writes
    distinct output files keyed off each canonical RSID."""
    import pandas as pd

    def _df(records: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(records)

    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)

    # Override getReportSuites with two suites sharing a name. Both must point
    # at the same demo.prod-shaped data because all other mocked methods
    # (getDimensions, etc.) ignore rsid in this mock.
    handle.getReportSuites.return_value = _df(
        [
            {"rsid": "demo.prod", "name": "Shared Name"},
            {"rsid": "demo.dev", "name": "Shared Name"},
        ]
    )
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(
        rsid="Shared Name",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
    )
    assert rc == 0
    # Both output files exist, named after each canonical RSID
    assert (tmp_path / "demo.prod.json").exists()
    assert (tmp_path / "demo.dev.json").exists()

    captured = capsys.readouterr()
    assert "matches 2 report suites" in captured.out
    assert "generating SDR 1/2: demo.prod" in captured.out
    assert "generating SDR 2/2: demo.dev" in captured.out


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_json_to_stdout(mock_client_cls, env_creds, tmp_path: Path, capsys) -> None:
    """--format json --output - writes JSON to stdout, no 'wrote:' diagnostic."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="json",
        profile=None,
    )
    assert rc == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    # JSON SDR doc has report_suite, dimensions, etc.
    assert parsed["report_suite"]["rsid"] == "demo.prod"
    assert "wrote:" not in captured.out


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_csv_rejected(mock_client_cls, env_creds, tmp_path: Path, capsys) -> None:
    """--format csv --output - rejects (multi-file)."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="csv",
        profile=None,
    )
    assert rc == 15


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_excel_rejected(mock_client_cls, env_creds, tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="excel",
        profile=None,
    )
    assert rc == 15


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_alias_rejected(mock_client_cls, env_creds, tmp_path: Path) -> None:
    """--format all --output - rejects (multi-format)."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(
        handle=handle,
        company_id="testco",
    )

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="all",
        profile=None,
    )
    assert rc == 15


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_snapshot_writes_to_profile_dir(
    mock_client_cls,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """--snapshot --profile X persists envelope to <home>/.aa/orgs/X/snapshots/<rsid>/<ts>.json."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    profile_dir = fake_home / ".aa" / "orgs" / "prod"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.json").write_text(
        json.dumps(
            {
                "org_id": "O",
                "client_id": "C",
                "secret": "S",
                "scopes": "X",
            }
        )
    )

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path / "out",
        format_name="json",
        profile="prod",
        snapshot=True,
        snapshot_dir=fake_home / ".aa" / "orgs" / "prod" / "snapshots",
    )
    assert rc == 0
    snap_dir = fake_home / ".aa" / "orgs" / "prod" / "snapshots" / "demo.prod"
    assert snap_dir.exists()
    files = list(snap_dir.glob("*.json"))
    assert len(files) == 1


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_snapshot_without_profile_resolves_default(
    mock_client_cls,
    env_creds,
    tmp_path: Path,
) -> None:
    """v1.15.0 P1 fix: --snapshot without --profile now falls back to 'default'
    profile dir rather than returning CONFIG (10). The run proceeds past the
    snapshot-dir check (auth error or success), never CONFIG."""
    from aa_auto_sdr.core.exceptions import AuthError

    mock_client_cls.from_credentials.side_effect = AuthError("bad creds")
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        snapshot=True,
    )
    # Must NOT be CONFIG (10) — the profile check no longer fires.
    # We mock auth to fail cleanly (11) rather than reaching real network.
    assert rc != 10


# ---------------------------------------------------------------------------
# Pipe-path error envelope tests (v0.9 review fix #1)
# ---------------------------------------------------------------------------


def test_generate_pipe_no_creds_emits_envelope_to_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """ConfigError on pipe path must JSON-envelope to stderr; stdout must stay empty."""
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = cmd.run(rsid="demo.prod", output_dir=Path("-"), format_name="json", profile=None)
    assert rc == 10
    captured = capsys.readouterr()
    assert captured.out == ""  # stdout silent
    payload = json.loads(captured.err.strip())
    assert payload["error"]["code"] == 10
    assert payload["error"]["type"] == "ConfigError"


def test_generate_non_pipe_no_creds_prints_to_stderr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    """Non-pipe path keeps the legacy human-readable error on stdout."""
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == 10
    captured = capsys.readouterr()
    assert "error:" in captured.err


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_auth_error_emits_envelope(mock_client_cls, env_creds, capsys) -> None:
    """AuthError on pipe path → envelope on stderr, stdout silent."""
    from aa_auto_sdr.core.exceptions import AuthError

    mock_client_cls.from_credentials.side_effect = AuthError("bad client_id")
    rc = cmd.run(rsid="demo.prod", output_dir=Path("-"), format_name="json", profile=None)
    assert rc == 11
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err.strip())
    assert payload["error"]["code"] == 11
    assert payload["error"]["type"] == "AuthError"


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_non_pipe_auth_error_prints_to_stderr(mock_client_cls, env_creds, tmp_path, capsys) -> None:
    """Non-pipe path keeps the legacy `auth error: ...` on stdout."""
    from aa_auto_sdr.core.exceptions import AuthError

    mock_client_cls.from_credentials.side_effect = AuthError("bad client_id")
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == 11
    captured = capsys.readouterr()
    assert "auth error" in captured.err


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_snapshot_without_profile_no_longer_config_error(mock_client_cls, env_creds, capsys) -> None:
    """`--snapshot` without `--profile` on pipe path: v1.15.0 P1 fix means we no
    longer return CONFIG (10) at the profile check. Auth failure emits envelope
    with a non-10 code."""
    from aa_auto_sdr.core.exceptions import AuthError

    mock_client_cls.from_credentials.side_effect = AuthError("bad creds")
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="json",
        profile=None,
        snapshot=True,
    )
    # Must NOT be CONFIG (10) — the profile check no longer fires.
    assert rc != 10


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_pipe_unknown_rsid_emits_envelope(mock_client_cls, env_creds, capsys) -> None:
    """ReportSuiteNotFoundError on pipe path → envelope (already covered, but
    confirms the post-build path also stays envelope-correct)."""
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    rc = cmd.run(rsid="never-exists", output_dir=Path("-"), format_name="json", profile=None)
    assert rc == 13
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err.strip())
    assert payload["error"]["code"] == 13
    assert payload["error"]["type"] == "ReportSuiteNotFoundError"


# ---------------------------------------------------------------------------
# Non-pipe error-path tests (v0.9 coverage gate to 90%)
# ---------------------------------------------------------------------------


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_non_pipe_unknown_rsid_returns_13(mock_client_cls, env_creds, tmp_path, capsys) -> None:
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")
    rc = cmd.run(rsid="never-exists", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == 13
    assert "error:" in capsys.readouterr().err


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_non_pipe_runsingle_apierror(
    mock_client_cls, env_creds, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """ApiError inside the single.run_single loop on the file-output path → exit 12."""
    from aa_auto_sdr.core.exceptions import ApiError
    from aa_auto_sdr.pipeline import single

    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    def boom(**_kw):
        raise ApiError("rate limit")

    monkeypatch.setattr(single, "run_single", boom)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == 12
    assert "api error" in capsys.readouterr().err


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_non_pipe_runsingle_outputerror(
    mock_client_cls, env_creds, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """OutputError inside the single.run_single loop → exit 15."""
    from aa_auto_sdr.core.exceptions import OutputError
    from aa_auto_sdr.pipeline import single

    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    def boom(**_kw):
        raise OutputError("disk full")

    monkeypatch.setattr(single, "run_single", boom)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == 15


# ---------------------------------------------------------------------------
# v1.1 — --auto-snapshot / --auto-prune wiring
# ---------------------------------------------------------------------------


class TestAutoSnapshot:
    @patch("aa_auto_sdr.cli.commands.generate.AaClient")
    def test_auto_snapshot_without_profile_resolves_default(
        self,
        mock_client_cls,
        env_creds,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """v1.15.0 P1 fix: --auto-snapshot without --profile falls back to 'default'
        profile dir. No longer returns CONFIG (10) at the profile check."""
        from aa_auto_sdr.core.exceptions import AuthError

        mock_client_cls.from_credentials.side_effect = AuthError("bad creds")
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=tmp_path,
            format_name="excel",
            profile=None,
            auto_snapshot=True,
        )
        # Must NOT be CONFIG (10) — the profile check no longer fires.
        assert rc != 10

    @patch("aa_auto_sdr.cli.commands.generate.AaClient")
    def test_auto_snapshot_saves_once_with_profile(
        self,
        mock_client_cls,
        env_creds,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        raw = json.loads(FIXTURE.read_text())
        handle = _build_handle(raw)
        mock_client_cls.from_credentials.return_value = MagicMock(
            handle=handle,
            company_id="testco",
        )
        monkeypatch.setenv("HOME", str(tmp_path))
        prof_dir = tmp_path / ".aa" / "orgs" / "prod"
        prof_dir.mkdir(parents=True)
        (prof_dir / "config.json").write_text(
            json.dumps(
                {
                    "org_id": "O",
                    "client_id": "C",
                    "secret": "S",
                    "scopes": "X",
                }
            )
        )
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=tmp_path,
            format_name="excel",
            profile="prod",
            auto_snapshot=True,
            snapshot_dir=tmp_path / ".aa" / "orgs" / "prod" / "snapshots",
        )
        assert rc == 0
        snap_dir = tmp_path / ".aa" / "orgs" / "prod" / "snapshots" / "demo.prod"
        assert len(list(snap_dir.glob("*.json"))) == 1

    @patch("aa_auto_sdr.cli.commands.generate.AaClient")
    def test_auto_prune_applies_policy(
        self,
        mock_client_cls,
        env_creds,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        raw = json.loads(FIXTURE.read_text())
        handle = _build_handle(raw)
        mock_client_cls.from_credentials.return_value = MagicMock(
            handle=handle,
            company_id="testco",
        )
        monkeypatch.setenv("HOME", str(tmp_path))
        prof_dir = tmp_path / ".aa" / "orgs" / "prod"
        prof_dir.mkdir(parents=True)
        (prof_dir / "config.json").write_text(
            json.dumps(
                {
                    "org_id": "O",
                    "client_id": "C",
                    "secret": "S",
                    "scopes": "X",
                }
            )
        )
        snap_dir = tmp_path / ".aa" / "orgs" / "prod" / "snapshots" / "demo.prod"
        snap_dir.mkdir(parents=True)
        for day in ("20", "21", "22"):
            (snap_dir / f"2026-04-{day}T10-00-00+00-00.json").write_text("{}")
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=tmp_path,
            format_name="excel",
            profile="prod",
            auto_snapshot=True,
            auto_prune=True,
            keep_last=1,
            snapshot_dir=tmp_path / ".aa" / "orgs" / "prod" / "snapshots",
        )
        assert rc == 0
        # Auto-snapshot wrote 1 new; auto-prune --keep-last 1 leaves 1.
        assert len(list(snap_dir.glob("*.json"))) == 1

    @patch("aa_auto_sdr.cli.commands.generate.AaClient")
    def test_snapshot_and_auto_snapshot_collapse_to_one_save(
        self,
        mock_client_cls,
        env_creds,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        raw = json.loads(FIXTURE.read_text())
        handle = _build_handle(raw)
        mock_client_cls.from_credentials.return_value = MagicMock(
            handle=handle,
            company_id="testco",
        )
        monkeypatch.setenv("HOME", str(tmp_path))
        prof_dir = tmp_path / ".aa" / "orgs" / "prod"
        prof_dir.mkdir(parents=True)
        (prof_dir / "config.json").write_text(
            json.dumps(
                {
                    "org_id": "O",
                    "client_id": "C",
                    "secret": "S",
                    "scopes": "X",
                }
            )
        )
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=tmp_path,
            format_name="excel",
            profile="prod",
            snapshot=True,
            auto_snapshot=True,
            snapshot_dir=tmp_path / ".aa" / "orgs" / "prod" / "snapshots",
        )
        assert rc == 0
        snap_dir = tmp_path / ".aa" / "orgs" / "prod" / "snapshots" / "demo.prod"
        assert len(list(snap_dir.glob("*.json"))) == 1


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_filesystem_failure_returns_output_error(mock_client_cls, env_creds, tmp_path, monkeypatch, capsys):
    handle = _build_handle(json.loads(FIXTURE.read_text()))
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    def fail_replace(source, destination):
        raise PermissionError("destination locked")

    monkeypatch.setattr("aa_auto_sdr.core.atomic_io.os.replace", fail_replace)
    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="excel", profile=None)
    assert rc == 15
    err = capsys.readouterr().err
    assert "demo.prod" in err
    assert "excel" in err
    assert "destination locked" in err
    assert not list(tmp_path.glob(".*"))


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_pipe_with_run_summary_file_keeps_stdout_pure_json(mock_client_cls, env_creds, tmp_path: Path, capsys) -> None:
    # --output - promises stdout carries only the SDR JSON; the
    # "wrote run summary" notice belongs on stderr there.
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    summary = tmp_path / "summary.json"

    rc = cmd.run(
        rsid="demo.prod", output_dir=Path("-"), format_name="json", profile=None, run_summary_json=str(summary)
    )

    captured = capsys.readouterr()
    assert rc == 0
    assert json.loads(captured.out)["report_suite"]["rsid"] == "demo.prod"
    assert f"wrote run summary: {summary}" in captured.err
    assert summary.exists()


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_file_output_run_summary_notice_stays_on_stdout(mock_client_cls, env_creds, tmp_path: Path, capsys) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    summary = tmp_path / "summary.json"

    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None, run_summary_json=str(summary))

    assert rc == 0
    assert f"wrote run summary: {summary}" in capsys.readouterr().out


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_pipe_ambiguous_name_emits_json_envelope(mock_client_cls, env_creds, capsys) -> None:
    from aa_auto_sdr.core.exceptions import AmbiguousMatchError

    mock_client_cls.from_credentials.return_value = MagicMock(company_id="testco")
    exc = AmbiguousMatchError("identifier 'Demo' is ambiguous", candidates=[("a.prod", "Demo"), ("b.prod", "Demo")])
    with patch("aa_auto_sdr.cli.commands.generate.fetch.resolve_rsid", side_effect=exc):
        rc = cmd.run(rsid="Demo", output_dir=Path("-"), format_name="json", profile=None)

    captured = capsys.readouterr()
    assert rc == 13
    assert captured.out == ""
    envelope = json.loads(captured.err.strip())
    assert envelope["error"]["code"] == 13
    assert envelope["error"]["type"] == "AmbiguousMatchError"
    # An unattended caller needs the candidates to retry with one of them.
    assert "a.prod (Demo)" in envelope["error"]["message"]
    assert "b.prod (Demo)" in envelope["error"]["message"]


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_run_summary_write_failure_exits_output(mock_client_cls, env_creds, tmp_path: Path, capsys) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        run_summary_json=str(tmp_path / "missing" / "s.json"),
    )

    assert rc == 15
    assert "could not write run summary" in capsys.readouterr().err
    assert (tmp_path / "demo.prod.json").exists()


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_pipe_run_summary_write_failure_keeps_stdout_clean(mock_client_cls, env_creds, tmp_path: Path, capsys) -> None:
    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="json",
        profile=None,
        run_summary_json=str(tmp_path / "missing" / "s.json"),
    )

    out, err = capsys.readouterr()
    assert rc == 15
    assert json.loads(out)["report_suite"]["rsid"] == "demo.prod"
    envelope = json.loads(err.strip().splitlines()[-1])
    assert envelope["error"]["code"] == 15
    assert envelope["error"]["type"] == "FileNotFoundError"
    assert "No such file or directory" in envelope["error"]["message"]


_SECRET_TEXT = "client_secret=SUPERSECRET123"


def test_generate_file_path_auth_error_is_redacted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    from aa_auto_sdr.core.exceptions import AuthError

    monkeypatch.setattr(cmd.credentials, "resolve", lambda **_k: object())

    def boom(*_a, **_k):
        raise AuthError(f"token request failed: {_SECRET_TEXT}")

    monkeypatch.setattr(cmd.AaClient, "from_credentials", boom)
    rc = cmd.run(rsid="rs1", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == 11
    assert "SUPERSECRET123" not in capsys.readouterr().err


@patch("aa_auto_sdr.cli.commands.generate.single.run_single")
@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_generate_file_path_api_error_redacted_in_stderr_and_summary(
    mock_client_cls, mock_run_single, env_creds, tmp_path: Path, capsys
) -> None:
    from aa_auto_sdr.core.exceptions import ApiError

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    mock_run_single.side_effect = ApiError(f"fetch failed: {_SECRET_TEXT}")
    summary = tmp_path / "summary.json"
    rc = cmd.run(
        rsid="demo.prod",
        output_dir=tmp_path,
        format_name="json",
        profile=None,
        run_summary_json=str(summary),
    )
    assert rc == 12
    assert "SUPERSECRET123" not in capsys.readouterr().err
    assert "SUPERSECRET123" not in summary.read_text(encoding="utf-8")


# --- the resolve listing is reused for the report suite row (one listing call) ---


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_single_run_makes_one_get_report_suites_call(mock_client_cls, env_creds, tmp_path: Path) -> None:
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == 0
    assert handle.getReportSuites.call_count == 1
    assert "rsid_list" not in handle.getReportSuites.call_args.kwargs


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_pipe_run_makes_one_get_report_suites_call(mock_client_cls, env_creds, capsys) -> None:
    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    rc = cmd.run(rsid="demo.prod", output_dir=Path("-"), format_name="json", profile=None)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report_suite"]["rsid"] == "demo.prod"
    assert handle.getReportSuites.call_count == 1


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_multi_match_run_makes_one_get_report_suites_call(mock_client_cls, env_creds, tmp_path: Path) -> None:
    import pandas as pd

    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    handle.getReportSuites.return_value = pd.DataFrame(
        [{"rsid": "demo.prod", "name": "Shared Name"}, {"rsid": "demo.dev", "name": "Shared Name"}]
    )
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    rc = cmd.run(rsid="Shared Name", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == 0
    assert json.loads((tmp_path / "demo.dev.json").read_text())["report_suite"]["rsid"] == "demo.dev"
    assert handle.getReportSuites.call_count == 1


def _generate_json_with_and_without_reuse(tmp_path: Path, *, pipe: bool, capsys) -> list[dict]:
    """Run generate twice on the same fixture: once with the listing reused and
    once with fetch_report_suite forced back onto its filtered SDK call. Returns
    both JSON documents without their capture timestamp."""
    from aa_auto_sdr.api import fetch as fetch_mod

    raw = json.loads(FIXTURE.read_text())
    docs: list[dict] = []
    real = fetch_mod.fetch_report_suite

    def _sdk_only(client, rsid, **_kw):
        return real(client, rsid)

    for reuse in (True, False):
        handle = _build_handle(raw)
        out_dir = tmp_path / ("reuse" if reuse else "sdk")
        with (
            patch("aa_auto_sdr.cli.commands.generate.AaClient") as cls,
            patch.object(fetch_mod, "fetch_report_suite", real if reuse else _sdk_only),
        ):
            cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")
            rc = cmd.run(
                rsid="demo.prod",
                output_dir=Path("-") if pipe else out_dir,
                format_name="json",
                profile=None,
            )
        assert rc == 0
        assert handle.getReportSuites.call_count == (1 if reuse else 2)
        text = capsys.readouterr().out if pipe else (out_dir / "demo.prod.json").read_text()
        doc = json.loads(text)
        doc.pop("captured_at")
        docs.append(doc)
    return docs


def test_listing_reuse_does_not_change_file_output(env_creds, tmp_path: Path, capsys) -> None:
    reused, sdk = _generate_json_with_and_without_reuse(tmp_path, pipe=False, capsys=capsys)
    assert reused == sdk


def test_listing_reuse_does_not_change_pipe_output(env_creds, tmp_path: Path, capsys) -> None:
    reused, sdk = _generate_json_with_and_without_reuse(tmp_path, pipe=True, capsys=capsys)
    assert reused == sdk


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_listing_failure_keeps_message_and_exit_code(mock_client_cls, env_creds, tmp_path: Path, capsys) -> None:
    """The listing is still fetched inside the resolve step, so a listing
    failure reaches the same `except ApiError` arm as before (exit 12)."""
    from aa_auto_sdr.api.client import AaClient
    from aa_auto_sdr.api.resilience import RetryPolicy

    raw = json.loads(FIXTURE.read_text())
    handle = _build_handle(raw)
    handle.getReportSuites.side_effect = AttributeError("listing exploded")
    mock_client_cls.from_credentials.return_value = AaClient(
        handle=handle, company_id="testco", retry_policy=RetryPolicy(max_retries=0)
    )

    rc = cmd.run(rsid="demo.prod", output_dir=tmp_path, format_name="json", profile=None)
    assert rc == 12
    assert capsys.readouterr().err == "api error: fetch failed: AttributeError: listing exploded\n"
    assert handle.getReportSuites.call_count == 1


@pytest.fixture
def git_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """A commit identity for runners with no global user.name/user.email."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test User")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_pipe_path_git_commit_creates_commit(mock_client_cls, env_creds, git_identity, tmp_path: Path, capsys) -> None:
    """--output - with --git-commit commits the snapshot, like the file path,
    and stdout still carries only the SDR JSON."""
    import subprocess

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    snap = tmp_path / "snaps"

    rc = cmd.run(
        rsid="demo.prod",
        output_dir=Path("-"),
        format_name="json",
        profile=None,
        snapshot=True,
        git_commit=True,
        snapshot_dir=snap,
    )

    out, _err = capsys.readouterr()
    assert rc == 0
    assert json.loads(out)["report_suite"]["rsid"] == "demo.prod"
    assert (snap / ".git").is_dir()
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=snap, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    # The initial README commit plus the snapshot commit.
    assert len(log) == 2
    tracked = subprocess.run(
        ["git", "ls-files", "demo.prod"], cwd=snap, capture_output=True, text=True, check=True
    ).stdout.split()
    assert len(tracked) == 1


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_pipe_path_git_failure_exits_16_with_envelope(mock_client_cls, env_creds, tmp_path: Path, capsys) -> None:
    """A failed git step after the document is written leaves stdout holding
    the full SDR JSON and puts one JSON error envelope (code 16) on stderr."""
    from aa_auto_sdr.snapshot.git import GitOpResult

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    failed = GitOpResult(ok=False, error_kind="GitCommitError", error_message="index locked")

    with patch("aa_auto_sdr.snapshot.git.git_commit_snapshot", return_value=failed):
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=Path("-"),
            format_name="json",
            profile=None,
            git_commit=True,
            snapshot_dir=tmp_path / "snaps",
        )

    out, err = capsys.readouterr()
    assert rc == 16
    assert json.loads(out)["report_suite"]["rsid"] == "demo.prod"
    err_lines = err.strip().splitlines()
    assert len(err_lines) == 1
    envelope = json.loads(err_lines[0])
    assert envelope["error"]["code"] == 16
    assert "GitCommitError" in envelope["error"]["message"]
    assert "index locked" in envelope["error"]["message"]


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_pipe_path_git_message_is_used(mock_client_cls, env_creds, tmp_path: Path, capsys) -> None:
    """--git-message and --git-push reach the git step on the pipe path."""
    from aa_auto_sdr.snapshot.git import GitOpResult

    raw = json.loads(FIXTURE.read_text())
    mock_client_cls.from_credentials.return_value = MagicMock(handle=_build_handle(raw), company_id="testco")
    snap = tmp_path / "snaps"
    ok = GitOpResult(ok=True, committed=True, pushed=True, commit_sha="a" * 40)

    with patch("aa_auto_sdr.snapshot.git.git_commit_snapshot", return_value=ok) as mock_commit:
        rc = cmd.run(
            rsid="demo.prod",
            output_dir=Path("-"),
            format_name="json",
            profile=None,
            git_commit=True,
            git_push=True,
            git_message="nightly SDR",
            snapshot_dir=snap,
        )

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report_suite"]["rsid"] == "demo.prod"
    mock_commit.assert_called_once_with(snap, rsid="demo.prod", message="nightly SDR", push=True)
