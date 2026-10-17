"""Single and repeated identifiers preserve the same resolution results."""

from unittest.mock import MagicMock

import pytest

from aa_auto_sdr.api import fetch
from aa_auto_sdr.api.report_suite_index import ReportSuiteIndex
from aa_auto_sdr.api.resilience import RetryPolicy
from aa_auto_sdr.cli.commands import batch, inventory, stats


@pytest.mark.parametrize("command", [batch, stats, inventory])
@pytest.mark.parametrize("identifiers", [["Shared"], ["Shared", "other"]])
@pytest.mark.parametrize("preload_fails", [False, True])
def test_resolution_preload_paths(command, identifiers, preload_fails, monkeypatch, tmp_path):
    rows = [
        {"rsid": "one", "name": "Shared"},
        {"rsid": "two", "name": "Shared"},
        {"rsid": "other", "name": "Other"},
    ]
    monkeypatch.setattr(command.credentials, "resolve", lambda **_kwargs: object())
    client = MagicMock(retry_policy=RetryPolicy())
    client.handle.getReportSuites.return_value = rows
    monkeypatch.setattr(command.AaClient, "from_credentials", lambda *_args, **_kwargs: client)
    raw_calls = []

    def raw(client):
        raw_calls.append(client)
        if preload_fails and len(raw_calls) == 1:
            raise RuntimeError("preload unavailable")
        return rows

    monkeypatch.setattr(fetch, "fetch_report_suites_raw", raw)
    original = fetch.resolve_rsid
    resolutions = []

    class ResolutionComplete(BaseException):
        pass

    def resolve(client, identifier, **kwargs):
        preload = kwargs["preloaded_suites"]
        if preload_fails:
            assert preload is None
        elif len(identifiers) == 1:
            assert preload is rows
        else:
            assert isinstance(preload, ReportSuiteIndex)
        resolutions.append(original(client, identifier, **kwargs))
        if len(resolutions) == len(identifiers):
            raise ResolutionComplete
        return resolutions[-1]

    monkeypatch.setattr(fetch, "resolve_rsid", resolve)
    kwargs = {"rsids": identifiers, "profile": None, "format_name": "json"}
    if command is batch:
        kwargs["output_dir"] = tmp_path
    with pytest.raises(ResolutionComplete):
        command.run(**kwargs)
    assert resolutions == [(["one", "two"], True)] + ([(["other"], False)] if len(identifiers) > 1 else [])
    assert len(raw_calls) == 1
    assert client.handle.getReportSuites.call_count == (len(identifiers) if preload_fails else 0)
