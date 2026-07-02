"""format='raw' avoids the DataFrame NaN pollution on ragged segment rows."""

from __future__ import annotations

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.resilience import RetryPolicy


class _FakeHandle:
    def __init__(self, rows):
        self._rows = rows
        self.calls: list[dict] = []

    def getSegments(self, **kwargs):
        self.calls.append(kwargs)
        return list(self._rows)  # format='raw' => plain list of dicts

    def getCalculatedMetrics(self, **kwargs):
        self.calls.append(kwargs)
        return list(self._rows)


class _FakeClient:
    def __init__(self, rows):
        self.handle = _FakeHandle(rows)
        self.retry_policy = RetryPolicy()


def test_segments_ragged_rows_no_nan_pollution():
    # Row 1 is full; row 2 omits description/created/modified entirely.
    rows = [
        {
            "id": "s1",
            "name": "Full",
            "description": "d",
            "rsid": "rs",
            "definition": {"x": 1},
            "created": "2026-01-01",
            "modified": "2026-01-02",
        },
        {"id": "s2", "name": "Sparse", "rsid": "rs", "definition": {"y": 2}},
    ]
    client = _FakeClient(rows)
    out = fetch.fetch_segments(client, "rs")

    sparse = next(s for s in out if s.id == "s2")
    assert sparse.description is None  # not the string "nan"
    assert sparse.created is None
    assert sparse.modified is None
    # SDK called with raw format and the max page size.
    assert client.handle.calls[0]["format"] == "raw"
    assert client.handle.calls[0]["limit"] == 1000


def test_calculated_metrics_raw_and_limit():
    rows = [{"id": "cm1", "name": "M", "rsid": "rs", "definition": {}}]
    client = _FakeClient(rows)
    out = fetch.fetch_calculated_metrics(client, "rs")
    assert out[0].id == "cm1"
    assert client.handle.calls[0]["format"] == "raw"
    assert client.handle.calls[0]["limit"] == 1000


def test_dataframe_path_pollutes_but_raw_does_not():
    """Characterization: shows *why* format='raw' matters. This passes on its own
    (it exercises the helpers directly); the red→green driver is the two kwargs
    assertions above. Keep it as a guard against anyone reverting to the df path."""
    import pandas as pd

    from aa_auto_sdr.api.fetch import _records, _str_or_none

    # Ragged rows: the second lacks 'description'. DataFrame.to_dict fills NaN.
    df = pd.DataFrame([{"id": "a", "description": "d"}, {"id": "b"}])
    df_recs = _records(df)
    assert _str_or_none(df_recs[1], "description") == "nan"  # the bug (old df path)

    raw_recs = _records([{"id": "a", "description": "d"}, {"id": "b"}])
    assert _str_or_none(raw_recs[1], "description") is None  # raw path is clean
