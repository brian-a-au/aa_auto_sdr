"""asdict runs once per component, not once per column."""

from __future__ import annotations

from aa_auto_sdr.api import models
from aa_auto_sdr.output.writers import csv as csv_writer


def test_component_rows_calls_asdict_once_per_item(monkeypatch):
    items = [
        models.Segment(
            id=f"s{i}",
            name=f"S{i}",
            description=None,
            rsid="rs",
            owner_id=None,
            definition={},
            compatibility={},
            tags=[],
            created=None,
            modified=None,
            extra={},
        )
        for i in range(3)
    ]
    calls = {"n": 0}
    real_asdict = csv_writer.asdict

    def counting_asdict(obj):
        calls["n"] += 1
        return real_asdict(obj)

    monkeypatch.setattr(csv_writer, "asdict", counting_asdict)
    _headers, rows = csv_writer._component_rows(items)
    assert len(rows) == 3
    assert calls["n"] == 3  # once per item — was 3 * len(headers)
