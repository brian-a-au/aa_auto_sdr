"""JSON writer. Self-registers with the registry on import."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from aa_auto_sdr.core.json_io import write_json
from aa_auto_sdr.output.registry import register_writer
from aa_auto_sdr.sdr.document import SdrDocument

logger = logging.getLogger(__name__)


class JsonWriter:
    extension = ".json"

    def write(self, doc: SdrDocument, output_path: Path) -> list[Path]:
        paths, _ = self._write_and_retain_payload(doc, output_path)
        return paths

    def _write_and_retain_payload(self, doc: SdrDocument, output_path: Path) -> tuple[list[Path], dict[str, Any]]:
        started = time.monotonic()
        target = output_path if output_path.suffix == self.extension else output_path.with_suffix(self.extension)
        payload = doc.to_dict()
        # The file carries the derived definition fields and the references
        # appendix; the retained payload stays plain so snapshots never do.
        from aa_auto_sdr.sdr.definitions import enrich_payload

        write_json(target, enrich_payload(doc, payload))
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
        return [target], payload


register_writer("json", JsonWriter())
