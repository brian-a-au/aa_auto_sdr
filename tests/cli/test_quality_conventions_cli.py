"""CLI wiring for quality conventions: severity case, policy rules threading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_auto_sdr.cli.main import _dispatch, _resolve_retry_policy
from aa_auto_sdr.cli.parser import build_parser
from aa_auto_sdr.sdr.quality import NamingRule, QualityException, QualityRules


def _dispatch_argv(argv: list[str]) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    ns.retry_policy = _resolve_retry_policy(ns)
    return _dispatch(ns, parser, argv)


@pytest.mark.parametrize("raw", ["high", "High", "HIGH"])
def test_fail_on_quality_case_insensitive(raw: str) -> None:
    assert build_parser().parse_args(["rs1", "--fail-on-quality", raw]).fail_on_quality == "HIGH"


def _policy(tmp_path: Path) -> Path:
    p = tmp_path / "policy.json"
    p.write_text(
        json.dumps(
            {
                "fail_on_quality": "low",
                "naming": {"dimensions": {"case": "snake_case"}},
                "exceptions": [{"rule_id": "dq.stale_keyword.v1", "component_id": "evar1", "reason": "kept"}],
            },
        ),
    )
    return p


_EXPECTED = QualityRules(
    naming={"dimensions": NamingRule(case="snake_case")},
    exceptions=(QualityException(rule_id="dq.stale_keyword.v1", component_id="evar1", reason="kept"),),
)


def test_policy_rules_reach_generate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import aa_auto_sdr.cli.commands.generate as generate_mod

    captured: dict[str, object] = {}
    monkeypatch.setattr(generate_mod, "run", lambda **kw: captured.update(kw) or 0)
    assert _dispatch_argv(["rs1", "--quality-policy", str(_policy(tmp_path))]) == 0
    assert captured["fail_on_quality"] == "LOW"
    assert captured["quality_rules"] == _EXPECTED


def test_policy_rules_reach_batch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import aa_auto_sdr.cli.commands.batch as batch_mod

    captured: dict[str, object] = {}
    monkeypatch.setattr(batch_mod, "run", lambda **kw: captured.update(kw) or 0)
    assert _dispatch_argv(["--batch", "rs1", "rs2", "--quality-policy", str(_policy(tmp_path))]) == 0
    assert captured["quality_rules"] == _EXPECTED


def test_no_policy_passes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    import aa_auto_sdr.cli.commands.generate as generate_mod

    captured: dict[str, object] = {}
    monkeypatch.setattr(generate_mod, "run", lambda **kw: captured.update(kw) or 0)
    assert _dispatch_argv(["rs1"]) == 0
    assert captured["quality_rules"] is None
