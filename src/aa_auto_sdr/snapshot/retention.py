"""Pure retention policy for snapshot files: parse policy strings, select files to delete.

Pure module — no filesystem I/O. Caller passes in a list of paths and a policy;
gets back the subset to delete. Filename shape comes from
snapshot.store.captured_at_to_filename: `<ISO-8601 with colons-as-hyphens>.json`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aa_auto_sdr.core.exceptions import ConfigError

_DURATION_RE = re.compile(r"^(\d+)([hdw])$")
_UNIT_TO_HOURS = {"h": 1, "d": 24, "w": 24 * 7}
_TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})([+-]\d{2})-(\d{2})$",
)


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """Describes which snapshots to keep. Either or both rules may be set."""

    keep_last: int | None = None
    keep_since: timedelta | None = None

    def is_active(self) -> bool:
        return self.keep_last is not None or self.keep_since is not None


def parse_policy(*, keep_last: int | None, keep_since: str | None) -> RetentionPolicy:
    """Build a RetentionPolicy from CLI arg values.

    `keep_since` is `<int><h|d|w>` (e.g. `30d`). Raises ConfigError on bad input."""
    if keep_last is not None and keep_last < 1:
        raise ConfigError(f"--keep-last must be >= 1 (got {keep_last})")
    if keep_since is None:
        return RetentionPolicy(keep_last=keep_last, keep_since=None)
    m = _DURATION_RE.match(keep_since)
    if not m:
        raise ConfigError(
            f"--keep-since must be <int><h|d|w> (e.g. 30d, 12h, 4w); got '{keep_since}'",
        )
    n, unit = int(m.group(1)), m.group(2)
    delta = timedelta(hours=n * _UNIT_TO_HOURS[unit])
    return RetentionPolicy(keep_last=keep_last, keep_since=delta)


def select_for_deletion(
    files: list[Path],
    policy: RetentionPolicy,
    *,
    now: datetime | None = None,
) -> list[Path]:
    """Return the paths in `files` that should be deleted under `policy`.

    Files are interpreted as chronological by sorted filename (lexical sort
    matches chronological order due to the ISO-8601 stem). `now` is injectable
    for deterministic tests."""
    if not policy.is_active() or not files:
        return []
    sorted_files = sorted(files)
    to_delete: set[Path] = set()
    if policy.keep_last is not None:
        kept = sorted_files[-policy.keep_last:]
        to_delete.update(f for f in sorted_files if f not in kept)
    if policy.keep_since is not None:
        cutoff = (now or datetime.now(timezone.utc)) - policy.keep_since
        for f in sorted_files:
            ts = _restore_iso(f.stem)
            if ts < cutoff:
                to_delete.add(f)
    return sorted(to_delete)


def _restore_iso(stem: str) -> datetime:
    """`2026-04-26T17-29-01+00-00` → datetime(2026,4,26,17,29,1,tzinfo=+00:00).

    Returns datetime.min(UTC) for unparseable stems so they sort earliest
    (which causes keep_since policies to flag them for deletion)."""
    m = _TS_RE.match(stem)
    if not m:
        return datetime.min.replace(tzinfo=timezone.utc)
    iso = (
        f"{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}"
        f"{m.group(5)}:{m.group(6)}"
    )
    return datetime.fromisoformat(iso)
