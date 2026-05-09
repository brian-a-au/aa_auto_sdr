"""fetch_classification_datasets returns FetchOutcome — see spec §4.2."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from aa_auto_sdr.api import models
from aa_auto_sdr.api.fetch import fetch_classification_datasets


def _client_with_classifications(rows: list[dict] | Exception) -> MagicMock:
    handle = MagicMock()
    if isinstance(rows, Exception):
        handle.getClassificationDatasets.side_effect = rows
    else:
        handle.getClassificationDatasets.return_value = pd.DataFrame(rows)
    client = MagicMock()
    client.handle = handle
    client.retry_policy = MagicMock(max_retries=0, base_delay=0.0, max_delay=0.0)
    return client


def test_classifications_healthy_returns_healthy_outcome() -> None:
    client = _client_with_classifications(
        [{"id": "ds1", "name": "Marketing channels"}],
    )
    outcome = fetch_classification_datasets(client, "rs1")
    assert isinstance(outcome, models.FetchOutcome)
    assert outcome.status == "healthy"
    assert outcome.expansion_level is None
    assert len(outcome.data) == 1
    assert outcome.data[0].id == "ds1"


def test_classifications_sdk_exception_returns_degraded_outcome() -> None:
    client = _client_with_classifications(KeyError("content"))
    outcome = fetch_classification_datasets(client, "rs1")
    assert isinstance(outcome, models.FetchOutcome)
    assert outcome.status == "degraded"
    assert outcome.expansion_level is None
    assert outcome.data == []


def test_classifications_empty_endpoint_returns_healthy_with_empty_list() -> None:
    """Empty result from a healthy endpoint is healthy, not degraded."""
    client = _client_with_classifications([])
    outcome = fetch_classification_datasets(client, "rs1")
    assert outcome.status == "healthy"
    assert outcome.data == []
