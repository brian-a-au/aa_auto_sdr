"""Meta-test: every ExitCode has a ROWS row and an EXPLANATIONS entry."""

from __future__ import annotations

from aa_auto_sdr.core.exit_codes import EXPLANATIONS, ROWS, ExitCode


def test_rows_covers_every_enum_value() -> None:
    rows_codes = {code for code, _meaning in ROWS}
    enum_codes = set(ExitCode)
    assert rows_codes == enum_codes


def test_explanations_covers_every_enum_value() -> None:
    assert set(EXPLANATIONS) == set(ExitCode)


def test_no_orphan_rows_or_explanations() -> None:
    """ROWS and EXPLANATIONS must not contain entries for codes outside ExitCode."""
    rows_codes = {code for code, _meaning in ROWS}
    expl_codes = set(EXPLANATIONS)
    enum_codes = set(ExitCode)
    assert rows_codes <= enum_codes
    assert expl_codes <= enum_codes
