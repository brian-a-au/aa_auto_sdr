"""Writer protocol — every output format implements this."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from aa_auto_sdr.sdr.document import SdrDocument


class Writer(Protocol):
    """Renders an SdrDocument to a file (or stdout)."""

    extension: str

    def write(self, doc: SdrDocument, output_path: Path) -> Path:
        """Write `doc` to `output_path` (or a derived path). Return the actual path written."""
        ...
