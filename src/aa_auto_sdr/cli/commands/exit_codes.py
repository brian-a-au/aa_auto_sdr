"""--exit-codes (list table) and --explain-exit-code <CODE> (paragraph) handlers.

Both are fast-path-friendly: no pandas/aanalytics2 imports."""

from __future__ import annotations

from aa_auto_sdr.core.exit_codes import EXPLANATIONS, ROWS, ExitCode


def run_list_exit_codes() -> int:
    """Print every exit code with a one-line meaning."""
    print("Code  Meaning")
    print("----  ---------------------------------------------------------------")
    for code, meaning in ROWS:
        print(f"{code.value:>4}  {meaning}")
    print()
    print("Use `aa_auto_sdr --explain-exit-code <CODE>` for details on a specific code.")
    return ExitCode.OK.value


def run_explain_exit_code(code: int) -> int:
    """Print the multi-paragraph explanation for `code`. Returns 2 on unknown code."""
    try:
        ec = ExitCode(code)
    except ValueError:
        print(
            f"error: unknown exit code '{code}' (run --exit-codes for the list)",
            flush=True,
        )
        return ExitCode.USAGE.value

    meaning = next((m for c, m in ROWS if c == ec), "")
    print(f"Exit code {ec.value} — {meaning}")
    print()
    print(EXPLANATIONS[ec])
    return ExitCode.OK.value
