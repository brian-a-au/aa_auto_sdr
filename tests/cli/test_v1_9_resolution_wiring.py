"""--extended-fields and --name-match reach their consumers.

See spec §3.3 + §3.4.

NOTE: All command run() functions accept explicit keyword args (not an args
namespace), and cli/main.py is the adapter that maps ns.* → kwargs.  These
tests therefore target:
  - diff_cmd.run()  → compare() receives extended_fields
  - generate._run_impl() → fetch.resolve_rsid receives name_match
  - batch._run_impl()   → fetch.resolve_rsid receives name_match
  - inspect._list_per_component() → fetch.resolve_rsid receives name_match
  - inspect.run_describe_reportsuite() → fetch.resolve_rsid receives name_match
  - stats.run()         → fetch.resolve_rsid receives name_match
  - cli/main.py dispatch → each handler receives name_match / extended_fields
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from aa_auto_sdr.snapshot.models import DiffReport

# ---------------------------------------------------------------------------
# diff.run() — extended_fields forwarded to compare()
# ---------------------------------------------------------------------------


def test_diff_passes_extended_fields_to_compare(tmp_path: Path) -> None:
    """diff_cmd.run with extended_fields=True calls compare(..., extended_fields=True)."""
    snap = {
        "schema": "aa-sdr-snapshot/v3",
        "rsid": "rs1",
        "captured_at": "2026-05-09T00:00:00+00:00",
        "tool_version": "1.9.0",
        "degraded_components": [],
        "partial_components": {},
        "quality": None,
        "components": {"report_suite": {"rsid": "rs1", "name": "Test"}},
    }
    real_report = DiffReport(
        a_rsid="rs1",
        b_rsid="rs1",
        a_captured_at="2026-05-09T00:00:00+00:00",
        b_captured_at="2026-05-09T00:00:00+00:00",
        a_tool_version="1.9.0",
        b_tool_version="1.9.0",
    )

    with (
        patch("aa_auto_sdr.cli.commands.diff.compare") as compare_mock,
        patch("aa_auto_sdr.cli.commands.diff.resolve_snapshot") as resolve_mock,
    ):
        resolve_mock.return_value = snap
        compare_mock.return_value = real_report

        from aa_auto_sdr.cli.commands import diff as diff_cmd

        diff_cmd.run(
            a="snap_a",
            b="snap_b",
            format_name="json",
            output=str(tmp_path / "out.json"),
            profile=None,
            extended_fields=True,
        )

    assert compare_mock.called, "compare() was never called"
    call_kwargs = compare_mock.call_args.kwargs
    assert call_kwargs.get("extended_fields") is True, (
        f"compare() was not called with extended_fields=True; kwargs={call_kwargs}"
    )


def test_diff_passes_extended_fields_false_by_default(tmp_path: Path) -> None:
    """diff_cmd.run without extended_fields defaults to False in compare()."""
    snap = {
        "schema": "aa-sdr-snapshot/v3",
        "rsid": "rs1",
        "captured_at": "2026-05-09T00:00:00+00:00",
        "tool_version": "1.9.0",
        "degraded_components": [],
        "partial_components": {},
        "quality": None,
        "components": {"report_suite": {"rsid": "rs1", "name": "Test"}},
    }
    real_report = DiffReport(
        a_rsid="rs1",
        b_rsid="rs1",
        a_captured_at="2026-05-09T00:00:00+00:00",
        b_captured_at="2026-05-09T00:00:00+00:00",
        a_tool_version="1.9.0",
        b_tool_version="1.9.0",
    )

    with (
        patch("aa_auto_sdr.cli.commands.diff.compare") as compare_mock,
        patch("aa_auto_sdr.cli.commands.diff.resolve_snapshot") as resolve_mock,
    ):
        resolve_mock.return_value = snap
        compare_mock.return_value = real_report

        from aa_auto_sdr.cli.commands import diff as diff_cmd

        diff_cmd.run(
            a="snap_a",
            b="snap_b",
            format_name="json",
            output=str(tmp_path / "out.json"),
            profile=None,
        )

    assert compare_mock.called
    call_kwargs = compare_mock.call_args.kwargs
    assert call_kwargs.get("extended_fields") is False, f"default extended_fields should be False; kwargs={call_kwargs}"


# ---------------------------------------------------------------------------
# generate._run_impl() — name_match forwarded to fetch.resolve_rsid
# ---------------------------------------------------------------------------


def test_generate_passes_name_match_to_resolve_rsid(tmp_path: Path) -> None:
    """generate._run_impl with name_match='fuzzy' passes it to fetch.resolve_rsid."""
    from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError

    with (
        patch("aa_auto_sdr.cli.commands.generate.fetch.resolve_rsid") as resolve_mock,
        patch("aa_auto_sdr.cli.commands.generate.AaClient.from_credentials"),
        patch("aa_auto_sdr.cli.commands.generate.credentials.resolve"),
        patch("aa_auto_sdr.cli.commands.generate.registry") as mock_reg,
    ):
        # registry succeeds; resolve_rsid raises to stop execution after being called
        mock_reg.resolve_formats.return_value = ["json"]
        mock_reg.get_writer.return_value = MagicMock()
        mock_reg.bootstrap.return_value = None
        resolve_mock.side_effect = ReportSuiteNotFoundError("not found — test sentinel")

        from aa_auto_sdr.cli.commands import generate as gen_cmd

        gen_cmd.run(
            rsid="My Suite Name",
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            name_match="fuzzy",
        )

    assert resolve_mock.called, "fetch.resolve_rsid was never called"
    assert any(call.kwargs.get("name_match") == "fuzzy" for call in resolve_mock.call_args_list), (
        f"resolve_rsid not called with name_match='fuzzy'; calls={resolve_mock.call_args_list}"
    )


def test_generate_name_match_default_insensitive(tmp_path: Path) -> None:
    """generate._run_impl without name_match defaults to 'insensitive'."""
    from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError

    with (
        patch("aa_auto_sdr.cli.commands.generate.fetch.resolve_rsid") as resolve_mock,
        patch("aa_auto_sdr.cli.commands.generate.AaClient.from_credentials"),
        patch("aa_auto_sdr.cli.commands.generate.credentials.resolve"),
        patch("aa_auto_sdr.cli.commands.generate.registry") as mock_reg,
    ):
        mock_reg.resolve_formats.return_value = ["json"]
        mock_reg.get_writer.return_value = MagicMock()
        mock_reg.bootstrap.return_value = None
        resolve_mock.side_effect = ReportSuiteNotFoundError("not found — test sentinel")

        from aa_auto_sdr.cli.commands import generate as gen_cmd

        gen_cmd.run(
            rsid="rs1",
            output_dir=tmp_path,
            format_name="json",
            profile=None,
        )

    assert resolve_mock.called
    # Default should be 'insensitive' (or absent, which fetch.py defaults to 'insensitive')
    for call in resolve_mock.call_args_list:
        nm = call.kwargs.get("name_match", "insensitive")
        assert nm == "insensitive", f"unexpected default name_match={nm!r}"


# ---------------------------------------------------------------------------
# batch._run_impl() — name_match forwarded to fetch.resolve_rsid
# ---------------------------------------------------------------------------


def test_batch_passes_name_match_to_resolve_rsid(tmp_path: Path) -> None:
    """batch._run_impl with name_match='exact' passes it to fetch.resolve_rsid."""
    from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError

    with (
        patch("aa_auto_sdr.cli.commands.batch.fetch.resolve_rsid") as resolve_mock,
        patch("aa_auto_sdr.cli.commands.batch.AaClient.from_credentials"),
        patch("aa_auto_sdr.cli.commands.batch.credentials.resolve"),
        patch("aa_auto_sdr.cli.commands.batch.registry") as mock_reg,
    ):
        mock_reg.resolve_formats.return_value = ["json"]
        mock_reg.get_writer.return_value = MagicMock()
        mock_reg.bootstrap.return_value = None
        # Let resolve_rsid succeed to capture the call, then raise to stop execution
        resolve_mock.side_effect = ReportSuiteNotFoundError("not found — test sentinel")

        from aa_auto_sdr.cli.commands import batch as batch_cmd

        batch_cmd.run(
            rsids=["some_suite"],
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            name_match="exact",
        )

    assert resolve_mock.called, "fetch.resolve_rsid was never called"
    assert any(call.kwargs.get("name_match") == "exact" for call in resolve_mock.call_args_list), (
        f"resolve_rsid not called with name_match='exact'; calls={resolve_mock.call_args_list}"
    )


# ---------------------------------------------------------------------------
# inspect._list_per_component() — name_match forwarded to fetch.resolve_rsid
# ---------------------------------------------------------------------------


def test_inspect_list_metrics_passes_name_match(tmp_path: Path) -> None:
    """inspect.run_list_metrics passes name_match to fetch.resolve_rsid."""
    with patch("aa_auto_sdr.cli.commands.inspect.fetch.resolve_rsid") as resolve_mock:
        resolve_mock.return_value = (["rs1"], False)
        with (
            patch("aa_auto_sdr.cli.commands.inspect._bootstrap") as bootstrap_mock,
            patch("aa_auto_sdr.cli.commands.inspect.fetch.fetch_metrics") as fetch_mock,
        ):
            bootstrap_mock.return_value = (MagicMock(), 0)
            fetch_mock.return_value = []

            from aa_auto_sdr.cli.commands import inspect as inspect_cmd

            inspect_cmd.run_list_metrics(
                identifier="My Metrics Suite",
                profile=None,
                format_name="json",
                output=str(tmp_path / "out.json"),
                name_filter=None,
                name_exclude=None,
                sort_field=None,
                limit=None,
                name_match="fuzzy",
            )

    assert resolve_mock.called, "fetch.resolve_rsid was never called"
    assert any(call.kwargs.get("name_match") == "fuzzy" for call in resolve_mock.call_args_list), (
        f"resolve_rsid not called with name_match='fuzzy'; calls={resolve_mock.call_args_list}"
    )


def test_inspect_describe_reportsuite_passes_name_match(tmp_path: Path) -> None:
    """inspect.run_describe_reportsuite passes name_match to fetch.resolve_rsid."""
    with patch("aa_auto_sdr.cli.commands.inspect.fetch.resolve_rsid") as resolve_mock:
        resolve_mock.return_value = (["rs1"], False)
        with (
            patch("aa_auto_sdr.cli.commands.inspect._bootstrap") as bootstrap_mock,
            patch("aa_auto_sdr.cli.commands.inspect.fetch.fetch_report_suite") as rs_mock,
            patch("aa_auto_sdr.cli.commands.inspect.fetch.fetch_dimensions", return_value=[]),
            patch("aa_auto_sdr.cli.commands.inspect.fetch.fetch_metrics", return_value=[]),
            patch("aa_auto_sdr.cli.commands.inspect.fetch.fetch_segments", return_value=[]),
            patch("aa_auto_sdr.cli.commands.inspect.fetch.fetch_calculated_metrics", return_value=[]),
            patch("aa_auto_sdr.cli.commands.inspect.fetch.fetch_virtual_report_suites") as vrs_mock,
            patch("aa_auto_sdr.cli.commands.inspect.fetch.fetch_classification_datasets") as cls_mock,
        ):
            bootstrap_mock.return_value = (MagicMock(), 0)
            rs_mock.return_value = MagicMock(
                rsid="rs1",
                name="Test",
                timezone="UTC",
                currency="USD",
                parent_rsid=None,
            )
            vrs_outcome = MagicMock()
            vrs_outcome.status = "healthy"
            vrs_outcome.data = []
            vrs_outcome.expansion_level = None
            vrs_mock.return_value = vrs_outcome
            cls_outcome = MagicMock()
            cls_outcome.status = "healthy"
            cls_outcome.data = []
            cls_outcome.expansion_level = None
            cls_mock.return_value = cls_outcome

            from aa_auto_sdr.cli.commands import inspect as inspect_cmd

            inspect_cmd.run_describe_reportsuite(
                identifier="My Suite",
                profile=None,
                format_name="json",
                output=str(tmp_path / "out.json"),
                name_match="exact",
            )

    assert resolve_mock.called, "fetch.resolve_rsid was never called"
    assert any(call.kwargs.get("name_match") == "exact" for call in resolve_mock.call_args_list), (
        f"resolve_rsid not called with name_match='exact'; calls={resolve_mock.call_args_list}"
    )


# ---------------------------------------------------------------------------
# stats.run() — name_match forwarded to fetch.resolve_rsid
# ---------------------------------------------------------------------------


def test_stats_passes_name_match_to_resolve_rsid() -> None:
    """stats.run with name_match='fuzzy' passes it to fetch.resolve_rsid."""
    from aa_auto_sdr.core.exceptions import ReportSuiteNotFoundError

    with (
        patch("aa_auto_sdr.cli.commands.stats.fetch.resolve_rsid") as resolve_mock,
        patch("aa_auto_sdr.cli.commands.stats.AaClient.from_credentials"),
        patch("aa_auto_sdr.cli.commands.stats.credentials.resolve"),
    ):
        # Raise after the call is captured so we don't need to stub downstream fetch
        resolve_mock.side_effect = ReportSuiteNotFoundError("not found — test sentinel")

        from aa_auto_sdr.cli.commands import stats as stats_cmd

        stats_cmd.run(
            rsids=["some_suite"],
            profile=None,
            format_name="table",
            name_match="fuzzy",
        )

    assert resolve_mock.called, "fetch.resolve_rsid was never called"
    assert any(call.kwargs.get("name_match") == "fuzzy" for call in resolve_mock.call_args_list), (
        f"resolve_rsid not called with name_match='fuzzy'; calls={resolve_mock.call_args_list}"
    )


# ---------------------------------------------------------------------------
# cli/main.py dispatch — ns.name_match and ns.extended_fields reach handlers
# ---------------------------------------------------------------------------


def test_main_dispatch_passes_name_match_to_generate() -> None:
    """cli.main dispatches ns.name_match to generate_cmd.run()."""
    with patch("aa_auto_sdr.cli.commands.generate.run") as run_mock:
        run_mock.return_value = 0
        from aa_auto_sdr.cli import main

        main.run(["rs1", "--name-match", "exact"])

    assert run_mock.called, "generate_cmd.run was never called"
    kwargs = run_mock.call_args.kwargs
    assert kwargs.get("name_match") == "exact", f"generate_cmd.run not called with name_match='exact'; kwargs={kwargs}"


def test_main_dispatch_passes_name_match_to_batch() -> None:
    """cli.main dispatches ns.name_match to batch_cmd.run()."""
    with patch("aa_auto_sdr.cli.commands.batch.run") as run_mock:
        run_mock.return_value = 0
        from aa_auto_sdr.cli import main

        main.run(["--batch", "rs1", "rs2", "--name-match", "fuzzy"])

    assert run_mock.called, "batch_cmd.run was never called"
    kwargs = run_mock.call_args.kwargs
    assert kwargs.get("name_match") == "fuzzy", f"batch_cmd.run not called with name_match='fuzzy'; kwargs={kwargs}"


def test_main_dispatch_passes_extended_fields_to_diff(tmp_path: Path) -> None:
    """cli.main dispatches ns.extended_fields to diff_cmd.run()."""
    snap_file_a = tmp_path / "a.json"
    snap_file_b = tmp_path / "b.json"
    snap_file_a.write_text("{}")
    snap_file_b.write_text("{}")

    with patch("aa_auto_sdr.cli.commands.diff.run") as run_mock:
        run_mock.return_value = 0
        from aa_auto_sdr.cli import main

        main.run(["--diff", str(snap_file_a), str(snap_file_b), "--extended-fields"])

    assert run_mock.called, "diff_cmd.run was never called"
    kwargs = run_mock.call_args.kwargs
    assert kwargs.get("extended_fields") is True, f"diff_cmd.run not called with extended_fields=True; kwargs={kwargs}"


def test_main_dispatch_passes_name_match_to_stats() -> None:
    """cli.main dispatches ns.name_match to stats_cmd.run()."""
    with patch("aa_auto_sdr.cli.commands.stats.run") as run_mock:
        run_mock.return_value = 0
        from aa_auto_sdr.cli import main

        main.run(["--stats", "--name-match", "exact"])

    assert run_mock.called, "stats_cmd.run was never called"
    kwargs = run_mock.call_args.kwargs
    assert kwargs.get("name_match") == "exact", f"stats_cmd.run not called with name_match='exact'; kwargs={kwargs}"


# ---------------------------------------------------------------------------
# AmbiguousMatchError → ExitCode.NOT_FOUND (exit code 13) + stderr candidate list
# Spec §3.3: ambiguous matches render candidates and return NOT_FOUND.
# ---------------------------------------------------------------------------


def test_generate_ambiguous_match_returns_not_found(tmp_path: Path, capsys) -> None:
    """generate._run_impl converts AmbiguousMatchError to exit code 13 with candidate list on stderr."""
    from aa_auto_sdr.core.exceptions import AmbiguousMatchError
    from aa_auto_sdr.core.exit_codes import ExitCode

    candidates = [("rs001", "Acme Prod"), ("rs002", "Acme Dev")]

    with (
        patch("aa_auto_sdr.cli.commands.generate.fetch.resolve_rsid") as resolve_mock,
        patch("aa_auto_sdr.cli.commands.generate.AaClient.from_credentials"),
        patch("aa_auto_sdr.cli.commands.generate.credentials.resolve"),
        patch("aa_auto_sdr.cli.commands.generate.registry") as mock_reg,
    ):
        mock_reg.resolve_formats.return_value = ["json"]
        mock_reg.get_writer.return_value = MagicMock()
        mock_reg.bootstrap.return_value = None
        resolve_mock.side_effect = AmbiguousMatchError("ambiguous", candidates=candidates)

        from aa_auto_sdr.cli.commands import generate as gen_cmd

        exit_code = gen_cmd.run(
            rsid="Acme",
            output_dir=tmp_path,
            format_name="json",
            profile=None,
        )

    assert exit_code == ExitCode.NOT_FOUND.value, f"Expected NOT_FOUND ({ExitCode.NOT_FOUND.value}), got {exit_code}"
    captured = capsys.readouterr()
    assert "rs001" in captured.err, "candidate rsid 'rs001' not in stderr"
    assert "Acme Prod" in captured.err, "candidate name 'Acme Prod' not in stderr"
    assert "rs002" in captured.err, "candidate rsid 'rs002' not in stderr"
    assert "ambiguous" in captured.err.lower(), "word 'ambiguous' not in stderr"


def test_batch_ambiguous_match_records_failure_continues(tmp_path: Path, capsys) -> None:
    """batch._run_impl records AmbiguousMatchError as a failure but continues processing other identifiers."""
    from aa_auto_sdr.core.exceptions import AmbiguousMatchError, ReportSuiteNotFoundError

    candidates = [("rs001", "Suite One"), ("rs002", "Suite Two")]

    def resolve_side_effect(client, identifier, *, name_match="insensitive", preloaded_suites=None):
        if identifier == "ambig_name":
            raise AmbiguousMatchError("ambiguous", candidates=candidates)
        raise ReportSuiteNotFoundError("not found")  # other identifiers also fail to keep test simple

    with (
        patch("aa_auto_sdr.cli.commands.batch.fetch.resolve_rsid", side_effect=resolve_side_effect),
        patch("aa_auto_sdr.cli.commands.batch.AaClient.from_credentials"),
        patch("aa_auto_sdr.cli.commands.batch.credentials.resolve"),
        patch("aa_auto_sdr.cli.commands.batch.registry") as mock_reg,
    ):
        mock_reg.resolve_formats.return_value = ["json"]
        mock_reg.get_writer.return_value = MagicMock()
        mock_reg.bootstrap.return_value = None

        from aa_auto_sdr.cli.commands import batch as batch_cmd

        batch_cmd.run(
            rsids=["ambig_name", "other_rsid"],
            output_dir=tmp_path,
            format_name="json",
            profile=None,
        )

    captured = capsys.readouterr()
    assert "rs001" in captured.err, "candidate rsid 'rs001' not in stderr"
    assert "Suite One" in captured.err, "candidate name 'Suite One' not in stderr"
    assert "ambiguous" in captured.err.lower(), "word 'ambiguous' not in stderr"


def test_inspect_list_ambiguous_match_returns_not_found(tmp_path: Path, capsys) -> None:
    """inspect._list_per_component converts AmbiguousMatchError to exit code 13 with candidate list on stderr."""
    from aa_auto_sdr.core.exceptions import AmbiguousMatchError
    from aa_auto_sdr.core.exit_codes import ExitCode

    candidates = [("rsA", "Suite Alpha"), ("rsB", "Suite Beta")]

    with patch("aa_auto_sdr.cli.commands.inspect.fetch.resolve_rsid") as resolve_mock:
        resolve_mock.side_effect = AmbiguousMatchError("ambiguous", candidates=candidates)
        with patch("aa_auto_sdr.cli.commands.inspect._bootstrap") as bootstrap_mock:
            bootstrap_mock.return_value = (MagicMock(), 0)

            from aa_auto_sdr.cli.commands import inspect as inspect_cmd

            exit_code = inspect_cmd.run_list_metrics(
                identifier="Suite",
                profile=None,
                format_name="json",
                output=str(tmp_path / "out.json"),
                name_filter=None,
                name_exclude=None,
                sort_field=None,
                limit=None,
            )

    assert exit_code == ExitCode.NOT_FOUND.value, f"Expected NOT_FOUND ({ExitCode.NOT_FOUND.value}), got {exit_code}"
    captured = capsys.readouterr()
    assert "rsA" in captured.err, "candidate rsid 'rsA' not in stderr"
    assert "Suite Alpha" in captured.err, "candidate name 'Suite Alpha' not in stderr"
    assert "ambiguous" in captured.err.lower(), "word 'ambiguous' not in stderr"


def test_inspect_describe_ambiguous_match_returns_not_found(tmp_path: Path, capsys) -> None:
    """inspect.run_describe_reportsuite converts AmbiguousMatchError to exit code 13 with candidate list on stderr."""
    from aa_auto_sdr.core.exceptions import AmbiguousMatchError
    from aa_auto_sdr.core.exit_codes import ExitCode

    candidates = [("rsX", "Suite X"), ("rsY", "Suite Y")]

    with patch("aa_auto_sdr.cli.commands.inspect.fetch.resolve_rsid") as resolve_mock:
        resolve_mock.side_effect = AmbiguousMatchError("ambiguous", candidates=candidates)
        with patch("aa_auto_sdr.cli.commands.inspect._bootstrap") as bootstrap_mock:
            bootstrap_mock.return_value = (MagicMock(), 0)

            from aa_auto_sdr.cli.commands import inspect as inspect_cmd

            exit_code = inspect_cmd.run_describe_reportsuite(
                identifier="Suite",
                profile=None,
                format_name="json",
                output=str(tmp_path / "out.json"),
            )

    assert exit_code == ExitCode.NOT_FOUND.value, f"Expected NOT_FOUND ({ExitCode.NOT_FOUND.value}), got {exit_code}"
    captured = capsys.readouterr()
    assert "rsX" in captured.err, "candidate rsid 'rsX' not in stderr"
    assert "Suite X" in captured.err, "candidate name 'Suite X' not in stderr"
    assert "ambiguous" in captured.err.lower(), "word 'ambiguous' not in stderr"


def test_stats_ambiguous_match_returns_not_found(capsys) -> None:
    """stats.run converts AmbiguousMatchError to exit code 13 with candidate list on stderr."""
    from aa_auto_sdr.core.exceptions import AmbiguousMatchError
    from aa_auto_sdr.core.exit_codes import ExitCode

    candidates = [("rs_p", "Prod Suite"), ("rs_q", "QA Suite")]

    with (
        patch("aa_auto_sdr.cli.commands.stats.fetch.resolve_rsid") as resolve_mock,
        patch("aa_auto_sdr.cli.commands.stats.AaClient.from_credentials"),
        patch("aa_auto_sdr.cli.commands.stats.credentials.resolve"),
    ):
        resolve_mock.side_effect = AmbiguousMatchError("ambiguous", candidates=candidates)

        from aa_auto_sdr.cli.commands import stats as stats_cmd

        exit_code = stats_cmd.run(
            rsids=["Suite"],
            profile=None,
            format_name="table",
        )

    assert exit_code == ExitCode.NOT_FOUND.value, f"Expected NOT_FOUND ({ExitCode.NOT_FOUND.value}), got {exit_code}"
    captured = capsys.readouterr()
    assert "rs_p" in captured.err, "candidate rsid 'rs_p' not in stderr"
    assert "Prod Suite" in captured.err, "candidate name 'Prod Suite' not in stderr"
    assert "ambiguous" in captured.err.lower(), "word 'ambiguous' not in stderr"
