"""core/exit_codes.py — central ExitCode IntEnum + ROWS + EXPLANATIONS."""

from __future__ import annotations

from aa_auto_sdr.core.exit_codes import EXPLANATIONS, ROWS, ExitCode


def test_every_existing_exit_code_in_enum() -> None:
    """Every code currently used by the CLI is in the enum."""
    for value in (0, 1, 2, 10, 11, 12, 13, 14, 15, 16):
        assert ExitCode(value).value == value


def test_intenum_compares_to_int() -> None:
    assert ExitCode.OK == 0
    assert ExitCode.SNAPSHOT == 16


def test_rows_has_one_entry_per_enum_value() -> None:
    """ROWS structure must be complete — used by --exit-codes table."""
    enum_values = {c.value for c in ExitCode}
    rows_values = {code.value for code, _meaning in ROWS}
    assert enum_values == rows_values


def test_rows_meanings_are_one_line() -> None:
    for _code, meaning in ROWS:
        assert "\n" not in meaning
        assert len(meaning) > 0
        assert len(meaning) < 80


def test_rows_sorted_by_code() -> None:
    codes = [c.value for c, _m in ROWS]
    assert codes == sorted(codes)


def test_explanations_complete() -> None:
    """EXPLANATIONS has an entry for every enum value."""
    for code in ExitCode:
        assert code in EXPLANATIONS
        assert len(EXPLANATIONS[code]) > 50


def test_explanations_have_what_to_try_section_for_failures() -> None:
    """Failure codes (>=1) should include a 'What to try:' remediation block."""
    for code in ExitCode:
        if code == ExitCode.OK:
            continue
        assert "What to try:" in EXPLANATIONS[code], f"missing remediation for {code.name}"


def test_auth_explanation_lists_verified_minimum_three_scopes() -> None:
    """M-3: AUTH explanation must say verified-minimum 3 scopes, not 5.

    Aligns with 4fcf155 and CLAUDE.md doctrine."""
    text = EXPLANATIONS[ExitCode.AUTH]
    assert "verified-minimum" in text
    assert "openid AdobeID" in text
    assert "additional_info.projectedProductContext" in text
    # The two recommended-but-not-required scopes should be called out as
    # *recommended* (not as part of the required set).
    assert "recommended" in text
    assert "read_organizations" in text
    assert "additional_info.job_function" in text
