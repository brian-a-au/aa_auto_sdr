"""--completion <shell> emits a static shell-completion script.

No argcomplete dependency. The user redirects stdout into their shell's
completion directory."""

from __future__ import annotations

import sys

from aa_auto_sdr.core.exit_codes import ExitCode


def _flags() -> list[str]:
    """Every option string the parser accepts, in parser order, minus ones it
    hides with argparse.SUPPRESS. Built from the parser so completions cannot
    drift from the CLI; argparse is the only import, so the fast path stays light."""
    import argparse

    from aa_auto_sdr.cli.parser import build_parser

    return [
        option
        for action in build_parser()._actions
        if action.help is not argparse.SUPPRESS
        for option in action.option_strings
    ]


def _bash_script() -> str:
    flags = " ".join(_flags())
    return f"""# bash completion for aa_auto_sdr / aa-auto-sdr
_aa_auto_sdr() {{
    local cur
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    COMPREPLY=( $(compgen -W "{flags}" -- "$cur") )
}}
complete -F _aa_auto_sdr aa_auto_sdr aa-auto-sdr
"""


def _zsh_script() -> str:
    flags = " ".join(_flags())
    return f"""#compdef aa_auto_sdr aa-auto-sdr
# zsh completion for aa_auto_sdr / aa-auto-sdr
_aa_auto_sdr() {{
    local -a flags
    flags=({flags})
    _describe 'flag' flags
}}
_aa_auto_sdr "$@"
"""


def _fish_script() -> str:
    lines = ["# fish completion for aa_auto_sdr / aa-auto-sdr"]
    for flag in _flags():
        if flag.startswith("--"):
            lines.append(f"complete -c aa_auto_sdr -c aa-auto-sdr -l {flag[2:]}")
        elif flag.startswith("-"):
            lines.append(f"complete -c aa_auto_sdr -c aa-auto-sdr -s {flag[1:]}")
    return "\n".join(lines) + "\n"


_TEMPLATES = {
    "bash": _bash_script,
    "zsh": _zsh_script,
    "fish": _fish_script,
}


def run_completion(shell: str) -> int:
    template = _TEMPLATES.get(shell)
    if template is None:
        print(
            f"error: unknown shell '{shell}' (must be bash, zsh, or fish)",
            file=sys.stderr,
            flush=True,
        )
        return ExitCode.USAGE.value
    print(template(), end="")
    return ExitCode.OK.value
