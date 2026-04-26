"""JSON writer. Self-registers with the registry on import."""

from __future__ import annotations

from pathlib import Path

from aa_auto_sdr.core.json_io import write_json
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument


class JsonWriter:
    extension = ".json"

    def write(self, doc: SdrDocument, output_path: Path) -> Path:
        target = output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)
        write_json(target, doc.to_dict())
        return target


register_writer("json", JsonWriter())
