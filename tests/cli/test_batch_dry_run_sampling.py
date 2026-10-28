"""A sampled batch dry run previews the sampled subset.

Sampling happens inside `pipeline.batch.run_batch`, and the dry-run branch
returns before that call. So the preview listed every resolved RSID while
the real run would have generated only `--sample N` of them, and the dry-run
run summary reported `sampled: false` with `total_available: 0`.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aa_auto_sdr.core.exit_codes import ExitCode

_RSIDS = ["demo.prod", "demo.staging", "demo.dev", "demo.qa"]


@pytest.fixture
def authed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_ID", "O")
    monkeypatch.setenv("CLIENT_ID", "C")
    monkeypatch.setenv("SECRET", "S")
    monkeypatch.setenv("SCOPES", "X")


@pytest.fixture
def resolving_client(monkeypatch: pytest.MonkeyPatch):
    """Resolve every identifier to itself without touching the SDK."""
    from aa_auto_sdr.cli.commands import batch as batch_cmd

    monkeypatch.setattr(batch_cmd.fetch, "fetch_report_suites_raw", lambda _client: [])
    monkeypatch.setattr(
        batch_cmd.fetch,
        "resolve_rsid",
        lambda _client, identifier, **_kwargs: ([identifier], False),
    )


def _dry_run(tmp_path: Path, *, summary_path: Path | None = None, **kwargs) -> int:
    from aa_auto_sdr.cli.commands import batch as batch_cmd

    with patch("aa_auto_sdr.cli.commands.batch.AaClient") as mock_client_cls:
        mock_client_cls.from_credentials.return_value = MagicMock(handle=MagicMock(), company_id="testco")
        return batch_cmd.run(
            rsids=list(_RSIDS),
            output_dir=tmp_path,
            format_name="json",
            profile=None,
            dry_run=True,
            run_summary_json=str(summary_path) if summary_path is not None else None,
            **kwargs,
        )


def _previewed(out: str) -> set[str]:
    return {rsid for rsid in _RSIDS if f"{rsid}.json" in out}


def test_dry_run_previews_only_the_sampled_subset(authed_env, resolving_client, tmp_path: Path, capsys) -> None:
    rc = _dry_run(tmp_path, sample_size=2, sample_seed=7)
    assert rc == ExitCode.OK.value
    assert len(_previewed(capsys.readouterr().out)) == 2


def test_dry_run_sampling_is_deterministic_for_a_seed(authed_env, resolving_client, tmp_path: Path, capsys) -> None:
    _dry_run(tmp_path, sample_size=2, sample_seed=7)
    first = _previewed(capsys.readouterr().out)
    _dry_run(tmp_path, sample_size=2, sample_seed=7)
    assert _previewed(capsys.readouterr().out) == first


def test_dry_run_summary_records_the_sample(authed_env, resolving_client, tmp_path: Path, capsys) -> None:
    summary_path = tmp_path / "summary.json"
    assert _dry_run(tmp_path, summary_path=summary_path, sample_size=2, sample_seed=7) == ExitCode.OK.value
    capsys.readouterr()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["sampled"] is True
    assert summary["sample_size"] == 2
    assert summary["sample_seed"] == 7
    assert summary["sample_strategy"] == "random"
    assert summary["total_available"] == len(_RSIDS)
    assert len(summary["rsids"]) == 2


def test_stratified_dry_run_previews_the_sampled_subset(authed_env, resolving_client, tmp_path: Path, capsys) -> None:
    rc = _dry_run(tmp_path, sample_size=2, sample_seed=7, sample_stratified=True)
    assert rc == ExitCode.OK.value
    assert len(_previewed(capsys.readouterr().out)) == 2


def test_unsampled_dry_run_still_previews_every_rsid(authed_env, resolving_client, tmp_path: Path, capsys) -> None:
    summary_path = tmp_path / "summary.json"
    assert _dry_run(tmp_path, summary_path=summary_path) == ExitCode.OK.value
    assert _previewed(capsys.readouterr().out) == set(_RSIDS)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["sampled"] is False
    assert summary["total_available"] == len(_RSIDS)


def test_sample_at_or_above_the_list_size_previews_every_rsid(
    authed_env, resolving_client, tmp_path: Path, capsys
) -> None:
    summary_path = tmp_path / "summary.json"
    assert _dry_run(tmp_path, summary_path=summary_path, sample_size=len(_RSIDS)) == ExitCode.OK.value
    assert _previewed(capsys.readouterr().out) == set(_RSIDS)
    # `run_batch` only marks a run sampled when the subset is smaller.
    assert json.loads(summary_path.read_text(encoding="utf-8"))["sampled"] is False
