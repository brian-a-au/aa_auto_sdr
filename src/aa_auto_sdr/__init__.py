"""aa_auto_sdr — Adobe Analytics SDR generator (API 2.0 only)."""

from aa_auto_sdr.core.version import __version__

__all__ = ["__version__", "main"]


def __getattr__(name: str):
    if name == "main":
        from aa_auto_sdr.__main__ import main as _main

        return _main
    raise AttributeError(f"module 'aa_auto_sdr' has no attribute {name!r}")
