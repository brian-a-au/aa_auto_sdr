"""PR comment: names with line breaks stay on one line, and an oversized
block keeps the item lines that fit."""

from __future__ import annotations

from aa_auto_sdr.output.diff_renderers.pr_comment import render_pr_comment
from aa_auto_sdr.snapshot.models import (
    AddedRemovedItem,
    ComponentDiff,
    DiffReport,
    FieldDelta,
    ModifiedItem,
)

_INJECTED = "Line one\n\n</details>\n# Injected"


def _report(*components: ComponentDiff) -> DiffReport:
    return DiffReport(
        a_rsid="RS1",
        b_rsid="RS1",
        a_captured_at="2026-04-25T10:00:00+00:00",
        b_captured_at="2026-04-26T10:00:00+00:00",
        a_tool_version="1.1.0",
        b_tool_version="1.1.0",
        components=list(components),
    )


def _block_tag_lines(out: str) -> tuple[int, int]:
    lines = out.splitlines()
    return lines.count("<details>"), lines.count("</details>")


def test_added_removed_modified_names_with_line_breaks_stay_on_one_line() -> None:
    out = render_pr_comment(
        _report(
            ComponentDiff(
                component_type="segments",
                added=[AddedRemovedItem(id="s1", name=_INJECTED)],
                removed=[AddedRemovedItem(id="s2", name="Two\r\nlines\rhere")],
                modified=[ModifiedItem(id="s3", name=_INJECTED, deltas=[FieldDelta("name", "a", "b")])],
            )
        )
    )
    opens, closes = _block_tag_lines(out)
    assert opens == closes
    assert not [ln for ln in out.splitlines() if ln.startswith("# Injected")]
    assert out.count("- `s1` — Line one  </details> # Injected _(segments)_\n") == 1
    assert "- `s2` — Two lines here _(segments)_\n" in out
    assert out.count("- `s3` — Line one  </details> # Injected _(segments)_\n") == 1


def test_name_without_line_breaks_renders_as_before() -> None:
    out = render_pr_comment(
        _report(ComponentDiff(component_type="metrics", added=[AddedRemovedItem(id="m1", name="Page Views")]))
    )
    assert "- `m1` — Page Views _(metrics)_\n" in out


_BANNER = "\n\n*(truncated — additional changes not shown; pipe full diff to a file with `--format json`)*\n"


def test_oversized_added_block_keeps_the_items_that_fit() -> None:
    from aa_auto_sdr.output.diff_renderers.pr_comment import LENGTH_CAP

    big = ComponentDiff(
        component_type="segments",
        added=[AddedRemovedItem(id=f"s{i}", name="n" * 50) for i in range(2000)],
    )
    out = render_pr_comment(_report(big))
    assert len(out) <= LENGTH_CAP
    assert out.endswith("</details>" + _BANNER)
    item_lines = [ln for ln in out.splitlines() if ln.startswith("- `s")]
    assert len(item_lines) >= 100
    # Whole item lines, kept from the start of the list.
    assert item_lines == [f"- `s{i}` — {'n' * 50} _(segments)_" for i in range(len(item_lines))]
    assert "<summary>➕ Added components</summary>" in out  # noqa: RUF001
    opens, closes = _block_tag_lines(out)
    assert opens == closes


def test_oversized_modified_block_cuts_whole_items_with_their_deltas() -> None:
    from aa_auto_sdr.output.diff_renderers.pr_comment import LENGTH_CAP

    big = ComponentDiff(
        component_type="metrics",
        modified=[
            ModifiedItem(
                id=f"m{i}",
                name=f"M{i}",
                deltas=[FieldDelta("name", f"old{i}", f"new{i}"), FieldDelta("description", "a", "b")],
            )
            for i in range(2000)
        ],
    )
    out = render_pr_comment(_report(big))
    assert len(out) <= LENGTH_CAP
    assert out.endswith("</details>" + _BANNER)
    lines = out.splitlines()
    items = [ln for ln in lines if ln.startswith("- `m")]
    assert len(items) >= 100
    # The last kept item still has both of its delta lines.
    last = lines.index(items[-1])
    assert lines[last + 1].startswith("  - `name`")
    assert lines[last + 2].startswith("  - `description`")
    assert lines[last + 3] == "</details>"


def test_block_that_fits_alone_is_still_dropped_whole() -> None:
    """Two blocks that each fit under the cap, but not together: the later
    block is dropped whole, as before."""
    added = [AddedRemovedItem(id=f"a{i}", name="n" * 40) for i in range(500)]
    removed = [AddedRemovedItem(id=f"r{i}", name="n" * 40) for i in range(500)]
    out = render_pr_comment(_report(ComponentDiff(component_type="segments", added=added, removed=removed)))
    assert out.endswith("</details>" + _BANNER)
    assert len([ln for ln in out.splitlines() if ln.startswith("- `a")]) == 500
    assert "Removed components" not in out


def _legacy_cut(body: str) -> str:
    """The cut before oversized blocks kept their items."""
    from aa_auto_sdr.output.diff_renderers.pr_comment import LENGTH_CAP

    truncated = body[: LENGTH_CAP - 200]
    last_close = truncated.rfind("</details>")
    if last_close >= 0:
        truncated = truncated[: last_close + len("</details>")]
    return truncated + _BANNER


def _uncapped(report: DiffReport, monkeypatch) -> str:
    from aa_auto_sdr.output.diff_renderers import pr_comment

    with monkeypatch.context() as m:
        m.setattr(pr_comment, "_enforce_cap", lambda body: body)
        return render_pr_comment(report)


def test_cut_outside_any_block_is_unchanged(monkeypatch) -> None:
    """A settings table over the cap comes before every block, so the cut is
    the same as before."""
    import dataclasses

    report = dataclasses.replace(
        _report(),
        report_suite_deltas=[FieldDelta(f"setting_{i}", "x" * 300, "y" * 300) for i in range(300)],
        settings_changes=300,
    )
    out = render_pr_comment(report)
    assert "Component breakdown" not in out
    assert out == _legacy_cut(_uncapped(report, monkeypatch))


def test_block_whose_first_item_does_not_fit_is_cut_as_before(monkeypatch) -> None:
    """One modified item larger than the cap: no whole item fits, so the
    block is dropped at the last `</details>` as before."""
    huge = ModifiedItem(id="m1", name="M1", deltas=[FieldDelta(f"f{i}", "a" * 300, "b" * 300) for i in range(200)])
    report = _report(ComponentDiff(component_type="metrics", modified=[huge]))
    out = render_pr_comment(report)
    assert "Modified components" not in out
    assert "Component breakdown" in out
    assert out == _legacy_cut(_uncapped(report, monkeypatch))


def test_block_that_fits_alone_matches_the_old_cut(monkeypatch) -> None:
    added = [AddedRemovedItem(id=f"a{i}", name="n" * 40) for i in range(500)]
    removed = [AddedRemovedItem(id=f"r{i}", name="n" * 40) for i in range(500)]
    report = _report(ComponentDiff(component_type="segments", added=added, removed=removed))
    assert render_pr_comment(report) == _legacy_cut(_uncapped(report, monkeypatch))
