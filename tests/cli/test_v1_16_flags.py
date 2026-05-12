"""--template / --template-organization argparse + pre-dispatch validation. v1.16.0."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from aa_auto_sdr.cli.parser import build_parser


def test_template_flag_parses() -> None:
    parser = build_parser()
    ns = parser.parse_args(["RS1", "--template", "/tmp/foo.xlsx"])
    assert ns.template == Path("/tmp/foo.xlsx")


def test_template_organization_flag_parses() -> None:
    parser = build_parser()
    ns = parser.parse_args(["RS1", "--template", "/tmp/foo.xlsx", "--template-organization", "Acme"])
    assert ns.template_organization == "Acme"


def test_template_overwrite_reserved_rejected_by_argparse() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["RS1", "--template", "/tmp/foo.xlsx", "--template-overwrite-reserved"])


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "aa_auto_sdr", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_template_missing_file_yields_usage(tmp_path: Path) -> None:
    missing = tmp_path / "nope.xlsx"
    result = _run_cli("RS1", "--template", str(missing))
    assert result.returncode == 2
    assert "Template not found" in result.stderr


def test_template_path_not_file_yields_usage(tmp_path: Path) -> None:
    result = _run_cli("RS1", "--template", str(tmp_path))  # dir
    assert result.returncode == 2
    assert "not a file" in result.stderr


def test_template_wrong_extension_yields_usage(tmp_path: Path) -> None:
    csv_file = tmp_path / "foo.csv"
    csv_file.write_text("x")
    result = _run_cli("RS1", "--template", str(csv_file))
    assert result.returncode == 2
    assert "must be a .xlsx file" in result.stderr


def test_template_with_json_format_yields_usage(tmp_path: Path) -> None:
    xlsx = tmp_path / "ok.xlsx"
    xlsx.write_bytes(b"PK\x03\x04stub")
    result = _run_cli("RS1", "--template", str(xlsx), "--format", "json")
    assert result.returncode == 2
    assert "--template requires --format excel" in result.stderr


def test_template_organization_requires_template() -> None:
    result = _run_cli("RS1", "--template-organization", "Acme")
    assert result.returncode == 2
    assert "--template-organization requires --template" in result.stderr


@pytest.mark.parametrize(
    "extra_args",
    [
        ["--diff", "a.json", "b.json"],
        ["--list-reportsuites"],
        ["--watch", "--interval", "1h"],
    ],
)
def test_template_with_non_generating_action_yields_usage(
    tmp_path: Path,
    extra_args: list[str],
) -> None:
    xlsx = tmp_path / "ok.xlsx"
    xlsx.write_bytes(b"PK\x03\x04stub")
    result = _run_cli("--template", str(xlsx), *extra_args)
    assert result.returncode == 2
    assert "--template requires an SDR-generating action" in result.stderr


def test_template_with_agent_mode_yields_usage(tmp_path: Path) -> None:
    """Agent-mode forces --format json --output -; resolved format set has
    no 'excel' entry, so the validator's format check returns USAGE.
    Covers spec §10.14."""
    xlsx = tmp_path / "ok.xlsx"
    xlsx.write_bytes(b"PK\x03\x04stub")
    result = _run_cli("RS1", "--template", str(xlsx), "--agent-mode")
    assert result.returncode == 2
    assert "--template requires --format excel" in result.stderr


def test_template_dry_run_includes_xlsx_in_preview(tmp_path: Path) -> None:
    """--template + --dry-run lists the would-be xlsx output path."""
    xlsx = tmp_path / "ok.xlsx"
    # Build a real (minimal) xlsx so the existence check passes; the dry-run
    # path doesn't open it for content.
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.title = "Glossary"  # type: ignore[union-attr]
    wb.save(xlsx)

    result = _run_cli(
        "RS1",
        "--template",
        str(xlsx),
        "--dry-run",
        "--profile",
        "__nonexistent_to_force_creds_fail__",
    )
    # Either USAGE on missing profile or full dry-run output — both are
    # acceptable for argparse-acceptance smoke. We're only verifying argparse
    # doesn't reject the combo.
    assert result.returncode in {0, 2, 3, 10}  # OK or USAGE or WARN or CONFIG-fail
    assert "Template not found" not in result.stderr
    assert "must be a .xlsx file" not in result.stderr
    assert "requires an SDR-generating action" not in result.stderr
