"""apply_filters: pure data pipeline (filter → exclude → sort → limit)."""

import pytest

from aa_auto_sdr.cli._filters import apply_filters

_RECORDS = [
    {"id": "evar1", "name": "User ID", "type": "string"},
    {"id": "evar2", "name": "Plan", "type": "string"},
    {"id": "evar3", "name": "Page Type", "type": "string"},
    {"id": "events", "name": "Custom Events", "type": "counter"},
]
_ALLOW = ("id", "name", "type")


def test_no_filters_returns_input_sorted_by_default_field() -> None:
    out = apply_filters(
        _RECORDS, name_filter=None, name_exclude=None, sort_field="id", limit=None, sort_field_allowlist=_ALLOW
    )
    assert [r["id"] for r in out] == ["evar1", "evar2", "evar3", "events"]


def test_filter_case_insensitive_substring_on_name() -> None:
    out = apply_filters(
        _RECORDS, name_filter="page", name_exclude=None, sort_field="id", limit=None, sort_field_allowlist=_ALLOW
    )
    assert [r["id"] for r in out] == ["evar3"]


def test_filter_matches_uppercase_input() -> None:
    out = apply_filters(
        _RECORDS, name_filter="USER", name_exclude=None, sort_field="id", limit=None, sort_field_allowlist=_ALLOW
    )
    assert [r["id"] for r in out] == ["evar1"]


def test_exclude_removes_matches() -> None:
    out = apply_filters(
        _RECORDS, name_filter=None, name_exclude="page", sort_field="id", limit=None, sort_field_allowlist=_ALLOW
    )
    assert [r["id"] for r in out] == ["evar1", "evar2", "events"]


def test_filter_and_exclude_combine() -> None:
    out = apply_filters(
        _RECORDS, name_filter="e", name_exclude="page", sort_field="id", limit=None, sort_field_allowlist=_ALLOW
    )
    # filter "e" matches User ID? yes. Plan? no. Page Type? yes (but page-excluded).
    # Custom Events? yes.
    assert [r["id"] for r in out] == ["evar1", "events"]


def test_sort_by_name() -> None:
    out = apply_filters(
        _RECORDS, name_filter=None, name_exclude=None, sort_field="name", limit=None, sort_field_allowlist=_ALLOW
    )
    assert [r["name"] for r in out] == ["Custom Events", "Page Type", "Plan", "User ID"]


def test_sort_field_not_in_allowlist_raises_valueerror() -> None:
    with pytest.raises(ValueError) as exc:
        apply_filters(
            _RECORDS,
            name_filter=None,
            name_exclude=None,
            sort_field="precision",
            limit=None,
            sort_field_allowlist=_ALLOW,
        )
    assert "precision" in str(exc.value)
    assert "id" in str(exc.value)  # allowlist mentioned


def test_limit_caps_after_sort() -> None:
    out = apply_filters(
        _RECORDS, name_filter=None, name_exclude=None, sort_field="id", limit=2, sort_field_allowlist=_ALLOW
    )
    assert [r["id"] for r in out] == ["evar1", "evar2"]


def test_limit_zero_returns_empty() -> None:
    out = apply_filters(
        _RECORDS, name_filter=None, name_exclude=None, sort_field="id", limit=0, sort_field_allowlist=_ALLOW
    )
    assert out == []


def test_limit_negative_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        apply_filters(
            _RECORDS, name_filter=None, name_exclude=None, sort_field="id", limit=-1, sort_field_allowlist=_ALLOW
        )


def test_empty_records_returns_empty() -> None:
    out = apply_filters([], name_filter="x", name_exclude=None, sort_field="id", limit=10, sort_field_allowlist=_ALLOW)
    assert out == []


def test_filter_treats_missing_name_as_empty_string() -> None:
    """A record with no `name` key should not match any non-empty filter substring."""
    records = [{"id": "x", "name": "Visible"}, {"id": "y"}]  # second has no name
    out = apply_filters(
        records, name_filter="z", name_exclude=None, sort_field="id", limit=None, sort_field_allowlist=("id", "name")
    )
    assert out == []


def test_sort_treats_missing_field_as_empty_string() -> None:
    """A record missing the sort field sorts as if its value were ''."""
    records = [{"id": "z", "name": "Z"}, {"id": "a"}, {"id": "m", "name": "M"}]
    out = apply_filters(
        records, name_filter=None, name_exclude=None, sort_field="name", limit=None, sort_field_allowlist=("id", "name")
    )
    # Empty string sorts before non-empty
    assert [r["id"] for r in out] == ["a", "m", "z"]
