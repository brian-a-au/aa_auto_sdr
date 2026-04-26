"""Fast-path entry point. Handles --version/--help/--exit-codes/--completion
without importing any heavy dependency. Delegates everything else to cli.main."""

from __future__ import annotations

import sys

from aa_auto_sdr.core.version import __version__

_FASTPATH_VERSION = {"-V", "--version"}
_FASTPATH_HELP = {"-h", "--help"}


def _print_version() -> int:
    print(f"aa_auto_sdr {__version__}")
    return 0


def _print_help() -> int:
    print(
        "aa_auto_sdr — Adobe Analytics SDR Generator (API 2.0 only)\n"
        "\n"
        "Usage:\n"
        "  aa_auto_sdr <RSID-or-name>           Generate SDR for one report suite\n"
        "  aa_auto_sdr --batch <RSID...>        Generate SDRs for multiple report suites\n"
        "  aa_auto_sdr --diff <a> <b>           Compare two snapshots (path|@ts|@latest|@previous|git:ref:path)\n"
        "  aa_auto_sdr <RSID> --snapshot --profile P  Generate + persist snapshot under ~/.aa/orgs/P/snapshots/\n"
        "  aa_auto_sdr --list-reportsuites      List all report suites visible to the org\n"
        "  aa_auto_sdr --list-metrics <RSID>    List metrics (also: --list-dimensions/segments/...)\n"
        "  aa_auto_sdr --describe-reportsuite <RSID>  Print metadata + per-component counts\n"
        "  aa_auto_sdr --profile-add <name>     Create a credentials profile\n"
        "  aa_auto_sdr --profile <name> ...     Use a named profile\n"
        "  aa_auto_sdr --show-config            Show resolved credentials source\n"
        "  aa_auto_sdr -V | --version           Print version\n"
        "  aa_auto_sdr -h | --help              Print this help\n"
        "\n"
        "v0.7: single + batch SDR generation, snapshot save, --diff, 5 formats.\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in _FASTPATH_VERSION:
        return _print_version()
    if args and args[0] in _FASTPATH_HELP:
        return _print_help()
    from aa_auto_sdr.cli.main import run

    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
