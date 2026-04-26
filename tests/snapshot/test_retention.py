"""Pure tests for snapshot.retention — parser + selector. No filesystem I/O."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from aa_auto_sdr.core.exceptions import ConfigError
from aa_auto_sdr.snapshot.retention import (
    RetentionPolicy,
    parse_policy,
    select_for_deletion,
)


class TestParsePolicy:
    def test_keep_last_only(self) -> None:
        p = parse_policy(keep_last=5, keep_since=None)
        assert p.keep_last == 5
        assert p.keep_since is None
        assert p.is_active()

    def test_keep_since_hours(self) -> None:
        p = parse_policy(keep_last=None, keep_since="12h")
        assert p.keep_since == timedelta(hours=12)

    def test_keep_since_days(self) -> None:
        p = parse_policy(keep_last=None, keep_since="30d")
        assert p.keep_since == timedelta(days=30)

    def test_keep_since_weeks(self) -> None:
        p = parse_policy(keep_last=None, keep_since="4w")
        assert p.keep_since == timedelta(weeks=4)

    def test_neither_inactive(self) -> None:
        p = parse_policy(keep_last=None, keep_since=None)
        assert not p.is_active()

    def test_keep_last_below_one_rejected(self) -> None:
        with pytest.raises(ConfigError, match=r"--keep-last must be >= 1"):
            parse_policy(keep_last=0, keep_since=None)

    def test_keep_since_bad_format(self) -> None:
        with pytest.raises(ConfigError, match=r"--keep-since"):
            parse_policy(keep_last=None, keep_since="forever")

    def test_keep_since_bad_unit(self) -> None:
        with pytest.raises(ConfigError):
            parse_policy(keep_last=None, keep_since="5y")


class TestSelectForDeletion:
    @staticmethod
    def _file(stem: str) -> Path:
        return Path(f"/snapshots/RS1/{stem}.json")

    def test_empty_input(self) -> None:
        assert select_for_deletion([], RetentionPolicy(keep_last=5)) == []

    def test_inactive_policy_keeps_everything(self) -> None:
        files = [self._file("2026-04-26T10-00-00+00-00")]
        assert select_for_deletion(files, RetentionPolicy()) == []

    def test_keep_last_drops_oldest(self) -> None:
        files = [
            self._file("2026-04-20T10-00-00+00-00"),
            self._file("2026-04-21T10-00-00+00-00"),
            self._file("2026-04-22T10-00-00+00-00"),
            self._file("2026-04-23T10-00-00+00-00"),
        ]
        deleted = select_for_deletion(files, RetentionPolicy(keep_last=2))
        assert deleted == [
            self._file("2026-04-20T10-00-00+00-00"),
            self._file("2026-04-21T10-00-00+00-00"),
        ]

    def test_keep_last_one_with_one_file_keeps_all(self) -> None:
        files = [self._file("2026-04-26T10-00-00+00-00")]
        assert select_for_deletion(files, RetentionPolicy(keep_last=1)) == []

    def test_keep_since_drops_old_files(self) -> None:
        now = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
        files = [
            self._file("2026-04-20T10-00-00+00-00"),  # 6 days old → drop
            self._file("2026-04-25T10-00-00+00-00"),  # 1 day old → keep
        ]
        deleted = select_for_deletion(
            files,
            RetentionPolicy(keep_since=timedelta(days=3)),
            now=now,
        )
        assert deleted == [self._file("2026-04-20T10-00-00+00-00")]

    def test_combined_policy_is_set_union_when_both_set(self) -> None:
        """Internal contract: when both rules are set on the dataclass, dropped
        files are the set-union of each rule's drops. The CLI rejects
        `--keep-last + --keep-since` at argparse so users can't reach this path,
        but the model remains flexible for any future internal use."""
        now = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
        files = [
            self._file("2026-04-20T10-00-00+00-00"),
            self._file("2026-04-21T10-00-00+00-00"),
            self._file("2026-04-25T10-00-00+00-00"),
            self._file("2026-04-26T10-00-00+00-00"),
        ]
        # keep_last=2 → drop the two oldest; keep_since=3d → drop the two >3d old
        # Result: union = three oldest.
        policy = RetentionPolicy(
            keep_last=2,
            keep_since=timedelta(days=3),
        )
        deleted = select_for_deletion(files, policy, now=now)
        assert deleted == [
            self._file("2026-04-20T10-00-00+00-00"),
            self._file("2026-04-21T10-00-00+00-00"),
        ]

    def test_malformed_filename_is_kept_not_deleted(self) -> None:
        """A stem that doesn't match _TS_RE returns datetime.max → never older
        than any cutoff → never flagged by keep_since. Fail-closed default
        prevents silent deletion of unrecognized filename shapes."""
        now = datetime(2026, 4, 26, tzinfo=UTC)
        files = [
            self._file("not-a-timestamp"),
            self._file("2026-04-26T10-00-00+00-00"),
        ]
        policy = RetentionPolicy(keep_since=timedelta(days=1))
        deleted = select_for_deletion(files, policy, now=now)
        # Only the parseable file is checked; it's < 1 day old → kept.
        # The malformed file returns datetime.max → kept.
        assert deleted == []

    def test_z_suffix_filename_parses_correctly(self) -> None:
        """Filenames with `Z` UTC suffix (alternate ISO form accepted by schema)
        must parse to a real datetime, not the fail-closed `datetime.max`."""
        now = datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC)
        files = [
            self._file("2026-04-20T10-00-00Z"),  # 6 days old — should be deleted
            self._file("2026-04-25T10-00-00Z"),  # 1 day old — should be kept
        ]
        policy = RetentionPolicy(keep_since=timedelta(days=3))
        deleted = select_for_deletion(files, policy, now=now)
        assert deleted == [self._file("2026-04-20T10-00-00Z")]
