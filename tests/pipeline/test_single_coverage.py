"""Single-RSID pipeline — coverage for template-fill and Notion writer config."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from aa_auto_sdr.api.client import AaClient
from aa_auto_sdr.pipeline import single

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_rs.json"


def _df(records: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(records)


@pytest.fixture
def mock_client() -> AaClient:
    raw = json.loads(FIXTURE.read_text())
    handle = MagicMock()
    handle.getReportSuites.return_value = _df([raw["report_suite"]])
    handle.getDimensions.return_value = _df(raw["dimensions"])
    handle.getMetrics.return_value = _df(raw["metrics"])
    handle.getSegments.return_value = _df(raw["segments"])
    handle.getCalculatedMetrics.return_value = _df(raw["calculated_metrics"])
    handle.getVirtualReportSuites.return_value = _df(raw["virtual_report_suites"])
    handle.getClassificationDatasets.return_value = _df(raw["classification_datasets"])
    return AaClient(handle=handle, company_id="testco")


class _FakeNotionWriter:
    """Stand-in for the singleton NotionWriter — no network, settable config."""

    extension = ".notion"

    def write(self, _doc: object, target: Path) -> list[Path]:
        return [target]


def test_run_single_template_path_threads_writer_config(mock_client: AaClient, tmp_path: Path) -> None:
    """template_path set: the excel-template writer's per-run attrs are populated
    even when 'excel-template' itself is not in the requested formats."""
    from aa_auto_sdr.output import registry

    template = tmp_path / "template.xlsx"

    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=["json"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.1.0",
        template_path=template,
        template_organization="Acme Corp",
    )

    assert result.success is True
    writer = registry.get_writer("excel-template")
    assert writer.template_path == template
    assert writer.organization == "Acme Corp"


def test_run_single_notion_path_threads_writer_config(
    mock_client: AaClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'notion' in formats: per-run config (force_new / database_id /
    disable_registry / company) is threaded onto the registered writer."""
    from aa_auto_sdr.output import registry

    real_get_writer = registry.get_writer
    fake = _FakeNotionWriter()

    def _fake_get_writer(name: str) -> object:
        if name == "notion":
            return fake
        return real_get_writer(name)

    monkeypatch.setattr(registry, "get_writer", _fake_get_writer)

    result = single.run_single(
        client=mock_client,
        rsid="demo.prod",
        formats=["notion"],
        output_dir=tmp_path,
        captured_at=datetime(2026, 4, 25, tzinfo=UTC),
        tool_version="0.1.0",
        notion_force_new=True,
        notion_registry_database="db-123",
        no_notion_registry=True,
        notion_company="AcmeCo",
    )

    assert result.success is True
    assert fake.force_new is True
    assert fake.database_id == "db-123"
    assert fake.disable_registry is True
    assert fake.company == "AcmeCo"
