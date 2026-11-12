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
