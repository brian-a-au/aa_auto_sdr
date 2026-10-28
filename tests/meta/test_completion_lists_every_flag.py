"""Shell completions must offer every long flag the parser accepts (except
ones it hides with argparse.SUPPRESS), so they cannot drift from the CLI."""

from __future__ import annotations

import argparse
import re

import pytest

from aa_auto_sdr.cli.commands.completion import run_completion
from aa_auto_sdr.cli.parser import build_parser


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_completion_offers_every_visible_parser_flag(shell: str, capsys) -> None:
    assert run_completion(shell) == 0
    out = capsys.readouterr().out
    flags = sorted(
        option
        for action in build_parser()._actions
        if action.help is not argparse.SUPPRESS
        for option in action.option_strings
        if option.startswith("--")
    )
    # fish declares long flags as `-l name`, bash and zsh list them as `--name`.
    tokens = [flag[2:] for flag in flags] if shell == "fish" else flags
    missing = [
        flag
        for flag, token in zip(flags, tokens, strict=True)
        if not re.search(r"(?<![\w-])" + re.escape(token) + r"(?![\w-])", out)
    ]
    assert not missing, f"flags missing from {shell} completion: {missing}"
