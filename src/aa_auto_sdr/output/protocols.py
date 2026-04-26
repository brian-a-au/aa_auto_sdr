"""Writer protocol — every output format implements this."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from aa_auto_sdr.sdr.document import SdrDocument


class Writer(Protocol):
    """Renders an SdrDocument to one or more files (or stdout in v0.3+)."""

    extension: str

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        """Write `doc` and return every path written.

        Single-file writers (json, excel, html, markdown) return a one-element
        list. Multi-file writers (csv) return one entry per file produced.
        Always non-empty.
        """
        ...
