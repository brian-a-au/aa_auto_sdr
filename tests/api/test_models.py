"""Normalized SDK-agnostic component dataclasses."""

from dataclasses import FrozenInstanceError

import pytest

from aa_auto_sdr.api import models


@pytest.mark.parametrize(
    ("cls", "kwargs"),
    [
        (
            models.ReportSuite,
            {
                "rsid": "x",
                "name": "n",
                "timezone": "T",
                "currency": "USD",
                "parent_rsid": None,
            },
        ),
        (
            models.Dimension,
            {
                "id": "x",
                "name": "n",
                "type": "t",
                "category": "c",
                "parent": "",
                "pathable": False,
                "description": None,
                "tags": [],
                "extra": {},
            },
        ),
        (
            models.Metric,
            {
                "id": "x",
                "name": "n",
                "type": "t",
                "category": "c",
                "precision": 0,
                "segmentable": True,
                "description": None,
                "tags": [],
                "data_group": None,
                "extra": {},
            },
        ),
    ],
)
def test_models_are_frozen(cls, kwargs) -> None:
    instance = cls(**kwargs)
    with pytest.raises(FrozenInstanceError):
        instance.name = "modified"  # type: ignore[misc]
