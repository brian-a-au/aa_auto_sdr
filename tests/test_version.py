"""Verify version is exposed and follows expected format."""

import re

import aa_auto_sdr


def test_version_is_exposed() -> None:
    assert hasattr(aa_auto_sdr, "__version__")


def test_version_matches_semver_dev() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[ab]\d+|rc\d+)?", aa_auto_sdr.__version__)


def test_version_is_0_1_0() -> None:
    assert aa_auto_sdr.__version__ == "0.1.0"
