"""Every CLI flag is either rejected with --render-from or explicitly allowed.

A new flag that lands in neither list fails here, so it cannot be silently
ignored by an offline render."""

from __future__ import annotations

from aa_auto_sdr.cli.main import _RENDER_FROM_ACCEPTED, _RENDER_FROM_CONFLICTS
from aa_auto_sdr.cli.parser import build_parser


def _action_group_dests() -> set[str]:
    """Destinations argparse already makes mutually exclusive with --render-from."""
    parser = build_parser()
    for group in parser._mutually_exclusive_groups:
        dests = {a.dest for a in group._group_actions}
        if "render_from" in dests:
            return dests - {"render_from"}
    raise AssertionError("--render-from is not in a mutually exclusive group")


def test_every_parser_dest_is_classified_for_render_from() -> None:
    # `rsids` (positional) has its own explicit rejection.
    parser = build_parser()
    all_dests = {a.dest for a in parser._actions} - {"help", "version"}
    conflicts = {attr for attr, _ in _RENDER_FROM_CONFLICTS}
    classified = conflicts | set(_RENDER_FROM_ACCEPTED) | _action_group_dests() | {"render_from", "rsids"}
    unclassified = sorted(all_dests - classified)
    assert not unclassified, (
        f"flags not classified for --render-from: {unclassified}. Add each to "
        "_RENDER_FROM_CONFLICTS (rejected) or _RENDER_FROM_ACCEPTED (honored) in cli/main.py."
    )


def test_classification_lists_name_real_dests_and_do_not_overlap() -> None:
    parser = build_parser()
    all_dests = {a.dest for a in parser._actions}
    conflicts = {attr for attr, _ in _RENDER_FROM_CONFLICTS}
    assert conflicts <= all_dests, sorted(conflicts - all_dests)
    assert set(_RENDER_FROM_ACCEPTED) <= all_dests, sorted(set(_RENDER_FROM_ACCEPTED) - all_dests)
    assert not conflicts & set(_RENDER_FROM_ACCEPTED)
    assert not _action_group_dests() & (conflicts | set(_RENDER_FROM_ACCEPTED))
