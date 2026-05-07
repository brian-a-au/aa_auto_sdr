"""JSON writer. Self-registers with the registry on import."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from aa_auto_sdr.core.json_io import write_json
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)


class JsonWriter:
    extension = ".json"

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        started = time.monotonic()
        target = output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)
        write_json(target, doc.to_dict())
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "output_write format=json output_path=%s count=1 duration_ms=%s",
            str(target),
            duration_ms,
            extra={
                "format": "json",
                "output_path": str(target),
                "count": 1,
                "duration_ms": duration_ms,
                "rsid": doc.report_suite.rsid,
            },
        )
        return [target]


register_writer("json", JsonWriter())
