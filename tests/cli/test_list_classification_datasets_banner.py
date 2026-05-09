"""--list-classification-datasets stderr banner on degraded fetch — see spec §4.4."""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

from aa_auto_sdr.api import models
from aa_auto_sdr.cli.commands.inspect import run_list_classification_datasets


def _outcome(status: str, expansion_level: str | None = None, rows: list[models.ClassificationDataset] | None = None):
    if status == "healthy":
        return models.FetchOutcome.healthy(rows or [])
    if status == "partial":
        return models.FetchOutcome.partial(rows or [], expansion_level=expansion_level or "minimal")
    return models.FetchOutcome.degraded()


def _stubs(*, fetch_returns: list, rsid: str = "demo.prod"):
    """fetch_returns: per-RSID call results (FetchOutcome instances)."""
    call_idx = {"i": 0}

    def fetch_side_effect(client, rsid_arg, **kwargs):
        idx = call_idx["i"]
        call_idx["i"] += 1
        return fetch_returns[idx]

    return [
        patch(
            "aa_auto_sdr.cli.commands.inspect._bootstrap",
            return_value=(MagicMock(), 0),
        ),
        patch(
            "aa_auto_sdr.cli.commands.inspect.fetch.resolve_rsid",
            return_value=([rsid], False),
        ),
        patch(
            "aa_auto_sdr.cli.commands.inspect.fetch.fetch_classification_datasets",
            side_effect=fetch_side_effect,
        ),
    ]


def _run(rsid: str = "demo.prod") -> tuple[str, str, int]:
    """Returns (stdout, stderr, exit_code)."""
    out_buf = StringIO()
    err_buf = StringIO()
    with patch("sys.stdout", out_buf), patch("sys.stderr", err_buf):
        rc = run_list_classification_datasets(
            identifier=rsid,
            profile=None,
            format_name="json",
            output=None,
            sort_field=None,
            limit=None,
            name_filter=None,
            name_exclude=None,
        )
    return out_buf.getvalue(), err_buf.getvalue(), rc


def test_healthy_no_banner() -> None:
    patches = _stubs(fetch_returns=[_outcome("healthy")])
    for p in patches:
        p.start()
    try:
        _stdout, stderr, rc = _run()
    finally:
        for p in patches:
            p.stop()
    assert "⚠" not in stderr
    assert "fetch degraded" not in stderr
    assert rc == 0


def test_degraded_emits_banner_exit_zero() -> None:
    patches = _stubs(fetch_returns=[_outcome("degraded")])
    for p in patches:
        p.start()
    try:
        _stdout, stderr, rc = _run()
    finally:
        for p in patches:
            p.stop()
    assert ("⚠ classifications fetch degraded for demo.prod — list may be incomplete; see logs/SDR_*.log") in stderr
    assert rc == 0  # exit code preserved — banner is informational


def test_partial_emits_banner_with_expansion_level() -> None:
    patches = _stubs(
        fetch_returns=[_outcome("partial", expansion_level="minimal")],
    )
    for p in patches:
        p.start()
    try:
        _stdout, stderr, rc = _run()
    finally:
        for p in patches:
            p.stop()
    assert "⚠ classifications fetch partial for demo.prod" in stderr
    assert "expansion_level=minimal" in stderr
    assert rc == 0


def test_multi_rsid_one_banner_per_non_healthy() -> None:
    """Multi-RSID name lookup: emit one banner per non-healthy RSID, none for healthy."""
    patches = _stubs(
        fetch_returns=[_outcome("healthy"), _outcome("degraded"), _outcome("healthy")],
    )
    # Override resolve_rsid to return three RSIDs
    patches[1] = patch(
        "aa_auto_sdr.cli.commands.inspect.fetch.resolve_rsid",
        return_value=(["rs.healthy1", "rs.degraded", "rs.healthy2"], True),
    )
    for p in patches:
        p.start()
    try:
        _stdout, stderr, rc = _run()
    finally:
        for p in patches:
            p.stop()
    # One banner for rs.degraded only — healthy RSIDs get no classification banner.
    assert "⚠ classifications fetch degraded for rs.degraded" in stderr
    # The multi-match disambiguation line names all RSIDs; check no *banner* for healthies.
    assert "classifications fetch degraded for rs.healthy1" not in stderr
    assert "classifications fetch degraded for rs.healthy2" not in stderr
    assert "classifications fetch partial for rs.healthy1" not in stderr
    assert "classifications fetch partial for rs.healthy2" not in stderr
    assert rc == 0
