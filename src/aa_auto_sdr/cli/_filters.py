"""Pure filter/exclude/sort/limit pipeline for list/inspect commands.

Single function. No I/O. No CLI knowledge. Trivially testable."""

from __future__ import annotations

from typing import Any


def apply_filters(
    records: list[dict[str, Any]],
    *,
    name_filter: str | None,
    name_exclude: str | None,
    sort_field: str,
    limit: int | None,
    sort_field_allowlist: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Apply filter, exclude, sort, and limit to a list of records.

    Pipeline order: filter → exclude → sort → limit. Stable sort.

    Filter and exclude both match `name_filter` / `name_exclude` against the
    `name` field (case-insensitive substring). Records with no `name` key never
    match any non-empty filter substring.

    Sort uses str() of the chosen field with empty-string fallback for missing.
    """
    if limit is not None and limit < 0:
        raise ValueError(f"--limit must be >= 0, got {limit}")
    if sort_field not in sort_field_allowlist:
        raise ValueError(
            f"--sort: '{sort_field}' not allowed; valid: {', '.join(sort_field_allowlist)}",
        )

    out = list(records)

    if name_filter:
        needle = name_filter.casefold()
        out = [r for r in out if needle in str(r.get("name", "")).casefold()]
    if name_exclude:
        needle = name_exclude.casefold()
        out = [r for r in out if needle not in str(r.get("name", "")).casefold()]

    out.sort(key=lambda r: str(r.get(sort_field, "")))

    if limit is not None:
        out = out[:limit]

    return out
