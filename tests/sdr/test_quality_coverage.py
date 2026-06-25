"""Coverage for edge branches in sdr/quality.py.

Covers _detect_case_style/_detect_prefix on degenerate inputs, the
empty-name skips in audit_naming and detect_stale, and the _id_of adapter
fallbacks (dataset_id-only and neither-id objects).
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock

from aa_auto_sdr.api.models import Dimension
from aa_auto_sdr.sdr.quality import (
    _detect_case_style,
    _detect_prefix,
    _id_of,
    audit_naming,
    detect_stale,
)


def _bundle(*, dimensions: list[Dimension] | None = None) -> MagicMock:
    b = MagicMock()
    b.dimensions = dimensions or []
    b.metrics = []
    b.segments = []
    b.calculated_metrics = []
    b.classifications = []
    b.virtual_report_suites = []
    return b


def _dim(id_: str, name: str) -> Dimension:
    return Dimension(
        id=id_,
        name=name,
        type="string",
        category=None,
        parent="",
        pathable=False,
        description=None,
    )


def test_detect_case_style_empty_string_is_other() -> None:
    assert _detect_case_style("") == "other"


def test_detect_prefix_slash_separated() -> None:
    assert _detect_prefix("variables/evar1") == "variables"


def test_audit_naming_skips_components_without_name_or_id() -> None:
    """A component with both name and id empty contributes nothing to the audit."""
    bundle = _bundle(dimensions=[_dim("", "")])
    audit = audit_naming(bundle)
    assert audit["total_components"] == 0


def test_detect_stale_skips_components_without_name_or_id() -> None:
    bundle = _bundle(dimensions=[_dim("", "")])
    assert detect_stale(bundle) == []


def test_id_of_falls_back_to_dataset_id() -> None:
    item = types.SimpleNamespace(dataset_id="ds-9")
    assert _id_of(item) == "ds-9"


def test_id_of_falls_back_to_repr_when_no_id_attrs() -> None:
    item = types.SimpleNamespace()
    assert _id_of(item) == repr(item)
