"""End-to-end CLI dispatch — covers the routing decisions in cli/main.run."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.cli.main import run

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def test_no_args_returns_usage_error(capsys) -> None:
    rc = run([])
    assert rc == 2
    err = capsys.readouterr().err + capsys.readouterr().out
    assert "rsid" in err.lower() or "usage" in err.lower()


def test_show_config_with_no_creds_returns_10(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for v in ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "AA_PROFILE"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.chdir(tmp_path)
    rc = run(["--show-config"])
    assert rc == 10


@patch("aa_auto_sdr.cli.commands.generate.AaClient")
def test_rsid_runs_generate(
    mock_client_cls,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import pandas as pd

    def _df(records: list[dict]) -> pd.DataFrame:
        return pd.DataFrame(records)

    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")

    rc = run(["demo.prod", "--format", "json", "--output-dir", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "demo.prod.json").exists()


@patch("aa_auto_sdr.cli.commands.batch.AaClient")
def test_batch_routes_to_commands_batch(
    mock_client_cls,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import pandas as pd

    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = pd.DataFrame([raw["report_suite"]])
    handle.getDimensions.return_value = pd.DataFrame(raw["dimensions"])
    handle.getMetrics.return_value = pd.DataFrame(raw["metrics"])
    handle.getSegments.return_value = pd.DataFrame(raw["segments"])
    handle.getCalculatedMetrics.return_value = pd.DataFrame(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = pd.DataFrame(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = pd.DataFrame(raw["classification_datasets"])
    mock_client_cls.from_credentials.return_value = MagicMock(handle=handle, company_id="testco")

    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")

    rc = run(["--batch", "demo.prod", "--format", "json", "--output-dir", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "demo.prod.json").exists()


def test_batch_with_output_dash_returns_15(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`--batch RSID --output -` is ambiguous (multi-SDR to single stream); reject."""
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")
    rc = run(["--batch", "demo.prod", "--output", "-"])
    assert rc == 15


def test_diff_routes_to_commands_diff(tmp_path: Path, capsys) -> None:
    """`run(["--diff", a, b])` should reach commands/diff.py and return 0 for two valid envelopes."""
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    payload = {
        "schema": "aa-sdr-snapshot/v1",
        "rsid": "demo.prod",
        "captured_at": "2026-04-20T10:00:00+00:00",
        "tool_version": "0.7.0",
        "components": {
            "report_suite": {
                "rsid": "demo.prod",
                "name": "demo.prod",
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
    a.write_text(json.dumps(payload, sort_keys=True))
    b.write_text(json.dumps({**payload, "captured_at": "2026-04-26T17:29:01+00:00"}, sort_keys=True))

    rc = run(["--diff", str(a), str(b)])
    assert rc == 0
    assert "SDR DIFF" in capsys.readouterr().out


def test_diff_with_positional_rsid_returns_2(capsys) -> None:
    """`--diff a b extra-rsid` is a usage error, not a silent ignore."""
    rc = run(["--diff", "a.json", "b.json", "extra-rsid"])
    assert rc == 2
    err = capsys.readouterr().out
    assert "positional" in err.lower() or "diff" in err.lower()


# ---------------------------------------------------------------------------
# Slow-path dispatch for v0.9 fast-path actions (coverage gate raise to 90%)
# ---------------------------------------------------------------------------


def test_exit_codes_via_slow_path(capsys) -> None:
    """`run([..., '--exit-codes'])` (not at argv[0]) must dispatch via slow path."""
    rc = run(["--profile", "anything", "--exit-codes"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Code  Meaning" in out


def test_explain_exit_code_via_slow_path(capsys) -> None:
    rc = run(["--profile", "anything", "--explain-exit-code", "11"])
    assert rc == 0
    assert "Exit code 11" in capsys.readouterr().out


def test_completion_via_slow_path(capsys) -> None:
    rc = run(["--profile", "anything", "--completion", "bash"])
    assert rc == 0
    assert "complete -F" in capsys.readouterr().out


def test_no_args_returns_usage_error_2(capsys) -> None:
    rc = run([])
    assert rc == 2


class TestV11Dispatch:
    def test_list_snapshots_dispatched(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        called: dict[str, object] = {}

        def _stub(*, profile, rsid, format_name):
            called["profile"] = profile
            called["rsid"] = rsid
            called["format_name"] = format_name
            return 0

        from aa_auto_sdr.cli.commands import snapshots as snap_cmd

        monkeypatch.setattr(snap_cmd, "list_run", _stub)
        rc = run(["--list-snapshots", "--profile", "prod"])
        assert rc == 0
        assert called["profile"] == "prod"

    def test_prune_snapshots_dispatched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: dict[str, object] = {}

        def _stub(*, profile, rsid, keep_last, keep_since, dry_run, **_v12):
            called.update(
                {
                    "profile": profile,
                    "rsid": rsid,
                    "keep_last": keep_last,
                    "keep_since": keep_since,
                    "dry_run": dry_run,
                }
            )
            return 0

        from aa_auto_sdr.cli.commands import snapshots as snap_cmd

        monkeypatch.setattr(snap_cmd, "prune_run", _stub)
        rc = run(
            [
                "--prune-snapshots",
                "--profile",
                "prod",
                "--keep-last",
                "5",
                "--dry-run",
            ]
        )
        assert rc == 0
        assert called["keep_last"] == 5
        assert called["dry_run"] is True

    def test_profile_list_dispatched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aa_auto_sdr.cli.commands import profiles as prof_cmd

        captured: dict[str, object] = {}

        def _stub(*, format_name=None, base=None):
            captured["format_name"] = format_name
            return 0

        monkeypatch.setattr(prof_cmd, "list_run", _stub)
        rc = run(["--profile-list", "--format", "json"])
        assert rc == 0
        assert captured["format_name"] == "json"

    def test_diff_passes_new_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aa_auto_sdr.cli.commands import diff as diff_cmd

        captured: dict[str, object] = {}

        def _stub(*, a, b, format_name, output, profile, side_by_side, summary, ignore_fields, **_v12):
            captured.update(
                {
                    "a": a,
                    "b": b,
                    "format_name": format_name,
                    "output": output,
                    "profile": profile,
                    "side_by_side": side_by_side,
                    "summary": summary,
                    "ignore_fields": ignore_fields,
                }
            )
            return 0

        monkeypatch.setattr(diff_cmd, "run", _stub)
        rc = run(
            [
                "--diff",
                "a.json",
                "b.json",
                "--side-by-side",
                "--summary",
                "--ignore-fields",
                "description,tags",
                "--format",
                "pr-comment",
            ]
        )
        assert rc == 0
        assert captured["side_by_side"] is True
        assert captured["summary"] is True
        assert captured["ignore_fields"] == frozenset({"description", "tags"})
        assert captured["format_name"] == "pr-comment"


class TestAutoBatchPositional:
    """v1.1 — multiple positional RSIDs auto-route to batch without --batch."""

    def test_two_positionals_routes_to_batch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd

        captured: dict[str, object] = {}

        def _stub(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        monkeypatch.setattr(batch_cmd, "run", _stub)
        rc = run(["rs1", "rs2", "--profile", "prod"])
        assert rc == 0
        assert captured["rsids"] == ["rs1", "rs2"]
        assert captured["profile"] == "prod"

    def test_three_positionals_with_mixed_rsid_and_name(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from aa_auto_sdr.cli.commands import batch as batch_cmd

        captured: dict[str, object] = {}

        def _stub(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        monkeypatch.setattr(batch_cmd, "run", _stub)
        rc = run(["dgeo1xxpnwcidadobestore", "Adobe Store", "demo.prod"])
        assert rc == 0
        # RSIDs and names pass through unchanged; batch's per-RSID resolver does name lookup.
        assert captured["rsids"] == ["dgeo1xxpnwcidadobestore", "Adobe Store", "demo.prod"]

    def test_single_positional_still_routes_to_generate(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from aa_auto_sdr.cli.commands import generate as generate_cmd

        captured: dict[str, object] = {}

        def _stub(**kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        monkeypatch.setattr(generate_cmd, "run", _stub)
        rc = run(["demo.prod"])
        assert rc == 0
        assert captured["rsid"] == "demo.prod"

    def test_batch_flag_greedy_consumes_all_rsids(self) -> None:
        """`--batch RS1 RS2 RS3` — argparse's nargs="+" is greedy, so all three RSIDs
        flow to ns.batch and ns.rsids stays empty. Confirms there's no parser-level
        ambiguity between --batch's args and the trailing positional."""
        from aa_auto_sdr.cli.parser import build_parser

        ns = build_parser().parse_args(["--batch", "rs1", "rs2", "rs3"])
        assert ns.batch == ["rs1", "rs2", "rs3"]
        assert ns.rsids == []

    def test_batch_flag_plus_positional_rejected(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Use the parser explicitly: --batch + positional rsid should error in main."""
        from aa_auto_sdr.cli.parser import build_parser

        ns = build_parser().parse_args(["rs1", "--batch", "rs2"])
        # Argparse populates both ns.rsids and ns.batch.
        assert ns.rsids == ["rs1"]
        assert ns.batch == ["rs2"]
        # Now run the dispatch — it should print the mutex error and return USAGE (2).
        rc = run(["rs1", "--batch", "rs2"])
        out = capsys.readouterr().out
        assert rc == 2
        assert "cannot combine --batch with positional RSIDs" in out

    def test_zero_positionals_returns_usage(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = run([])
        assert rc == 2

    def test_describe_reportsuite_with_extra_positional_rejects(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--describe-reportsuite takes its RSID inline; extras are a usage error
        rather than silently dropped."""
        rc = run(["--describe-reportsuite", "rs1", "rs2"])
        assert rc == 2
        assert "takes its RSID inline" in capsys.readouterr().out

    def test_list_metrics_with_extra_positional_rejects(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = run(["--list-metrics", "rs1", "rs2"])
        assert rc == 2
        assert "takes its RSID inline" in capsys.readouterr().out

    def test_profile_test_with_extra_positional_rejects(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = run(["--profile-test", "prod", "extra-arg"])
        assert rc == 2
        assert "takes its RSID inline" in capsys.readouterr().out

    def test_list_snapshots_with_two_positionals_rejects(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc = run(["--list-snapshots", "rs1", "rs2", "--profile", "prod"])
        assert rc == 2
        assert "at most one positional" in capsys.readouterr().out


class TestV12Dispatch:
    def test_stats_dispatched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aa_auto_sdr.cli.commands import stats as stats_cmd

        captured: dict[str, object] = {}

        def _stub(*, rsids, profile, format_name):
            captured["rsids"] = rsids
            captured["profile"] = profile
            captured["format_name"] = format_name
            return 0

        monkeypatch.setattr(stats_cmd, "run", _stub)
        rc = run(["--stats", "rs1", "rs2", "--profile", "prod"])
        assert rc == 0
        assert captured["rsids"] == ["rs1", "rs2"]
        assert captured["profile"] == "prod"

    def test_interactive_dispatched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aa_auto_sdr.cli.commands import interactive as interactive_cmd

        captured: dict[str, object] = {}

        def _stub(*, profile):
            captured["profile"] = profile
            return 0

        monkeypatch.setattr(interactive_cmd, "run", _stub)
        rc = run(["--interactive", "--profile", "prod"])
        assert rc == 0
        assert captured["profile"] == "prod"

    def test_config_status_dispatched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aa_auto_sdr.cli.commands import config as config_cmd

        captured: dict[str, object] = {}

        def _stub(*, profile):
            captured["profile"] = profile
            return 0

        monkeypatch.setattr(config_cmd, "config_status", _stub)
        rc = run(["--config-status"])
        assert rc == 0

    def test_sample_config_dispatched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aa_auto_sdr.cli.commands import config as config_cmd

        called = {"hit": False}

        def _stub():
            called["hit"] = True
            return 0

        monkeypatch.setattr(config_cmd, "sample_config", _stub)
        rc = run(["--sample-config"])
        assert rc == 0
        assert called["hit"] is True

    def test_diff_passes_v12_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aa_auto_sdr.cli.commands import diff as diff_cmd

        captured: dict[str, object] = {}

        def _stub(
            *,
            a,
            b,
            format_name,
            output,
            profile,
            side_by_side,
            summary,
            ignore_fields,
            quiet,
            labels,
            reverse,
            changes_only,
            show_only,
            max_issues,
            warn_threshold,
            color_theme="default",
        ):
            captured.update(
                {
                    "quiet": quiet,
                    "labels": labels,
                    "reverse": reverse,
                    "changes_only": changes_only,
                    "show_only": show_only,
                    "max_issues": max_issues,
                    "warn_threshold": warn_threshold,
                }
            )
            return 0

        monkeypatch.setattr(diff_cmd, "run", _stub)
        rc = run(
            [
                "--diff",
                "a.json",
                "b.json",
                "--quiet-diff",
                "--reverse-diff",
                "--diff-labels",
                "A=before",
                "B=after",
                "--changes-only",
                "--show-only",
                "metrics,dimensions",
                "--max-issues",
                "5",
                "--warn-threshold",
                "10",
            ]
        )
        assert rc == 0
        assert captured["quiet"] is True
        assert captured["reverse"] is True
        assert captured["labels"] == ("before", "after")
        assert captured["changes_only"] is True
        assert captured["show_only"] == frozenset({"metrics", "dimensions"})
        assert captured["max_issues"] == 5
        assert captured["warn_threshold"] == 10

    def test_generate_passes_v12_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aa_auto_sdr.cli.commands import generate as generate_cmd

        captured: dict[str, object] = {}

        def _stub(**kwargs):
            captured.update(kwargs)
            return 0

        monkeypatch.setattr(generate_cmd, "run", _stub)
        rc = run(["RS1", "--metrics-only", "--open", "-y"])
        assert rc == 0
        assert captured["metrics_only"] is True
        assert captured["open_after"] is True
        assert captured["assume_yes"] is True

    def test_profile_import_with_overwrite(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from aa_auto_sdr.cli.commands import profiles as prof_cmd

        captured: dict[str, object] = {}

        def _stub(name, file_path, *, base=None, overwrite=False):
            captured["name"] = name
            captured["file_path"] = file_path
            captured["overwrite"] = overwrite
            return 0

        monkeypatch.setattr(prof_cmd, "import_run", _stub)
        rc = run(["--profile-import", "prod", "/tmp/c.json", "--profile-overwrite"])
        assert rc == 0
        assert captured["overwrite"] is True


def test_diff_labels_without_a_b_prefix_passes_through(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """M-5: --diff-labels foo bar (no `A=`/`B=` prefix) is accepted; values pass
    through unchanged. The label-parsing code in cli/main.py uses
    .split('=', 1)[-1], which yields the original token when no '=' is present."""
    from aa_auto_sdr.cli.commands import diff as diff_cmd

    captured: dict = {}

    def _stub(**kwargs):
        captured.update(kwargs)
        return 0

    # The stub completely replaces diff_cmd.run, so resolve_snapshot is never
    # called — these files exist only to satisfy argparse's positional consumption.
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.json").write_text("{}")

    monkeypatch.setattr(diff_cmd, "run", _stub)
    rc = run(
        [
            "--diff",
            str(tmp_path / "a.json"),
            str(tmp_path / "b.json"),
            "--diff-labels",
            "foo",
            "bar",
        ],
    )
    assert rc == 0
    assert captured["labels"] == ("foo", "bar")


def test_run_summary_json_dash_with_output_dash_returns_output_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both --run-summary-json - and --output - want stdout — reject before any work."""
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")
    rc = run(
        [
            "demo.prod",
            "--format",
            "json",
            "--output",
            "-",
            "--run-summary-json",
            "-",
        ],
    )
    assert rc == 15  # ExitCode.OUTPUT
