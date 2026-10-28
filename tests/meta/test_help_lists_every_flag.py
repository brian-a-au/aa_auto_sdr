"""The fast-path `--help` text is hand-written in `__main__.py`, so it drifts
from the parser unless something checks it. Every long flag the parser
accepts (except ones it hides with argparse.SUPPRESS) must appear in it."""

from __future__ import annotations

import argparse
import re

from aa_auto_sdr.__main__ import _print_help
from aa_auto_sdr.cli.parser import build_parser


def test_help_lists_every_visible_parser_flag(capsys) -> None:
    _print_help()
    out = capsys.readouterr().out
    flags = sorted(
        option
        for action in build_parser()._actions
        if action.help is not argparse.SUPPRESS
        for option in action.option_strings
        if option.startswith("--")
    )
    missing = [flag for flag in flags if not re.search(re.escape(flag) + r"(?![\w-])", out)]
    assert not missing, f"flags missing from --help (__main__._print_help): {missing}"
