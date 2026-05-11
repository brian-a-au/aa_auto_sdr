"""generate_commit_message format invariants."""

from __future__ import annotations

from aa_auto_sdr.snapshot.git import generate_commit_message


class TestGenerateCommitMessage:
    def test_baseline_message(self) -> None:
        msg = generate_commit_message(
            rsid="rs_prod_us",
            captured_at="2026-05-11T14:00:00Z",
            change_summary=None,
        )
        lines = msg.splitlines()
        assert lines[0] == "SDR snapshot: rs_prod_us @ 2026-05-11T14:00:00Z"
        assert len(lines[0]) <= 72
        assert lines[1] == ""
        assert lines[2] == "Initial snapshot"
        assert "(watch cycle" not in msg

    def test_change_message_with_summary(self) -> None:
        msg = generate_commit_message(
            rsid="rs_a",
            captured_at="2026-05-11T15:00:00Z",
            change_summary={
                "added": 2,
                "removed": 0,
                "modified": 1,
                "unchanged": 100,
                "by_type": {
                    "dimensions": {"added": 2, "removed": 0, "modified": 1},
                    "metrics": {"added": 0, "removed": 0, "modified": 0},
                },
            },
        )
        assert "SDR snapshot: rs_a @ 2026-05-11T15:00:00Z" in msg
        assert "dimensions: +2 -0 ~1" in msg
        assert "metrics:    +0 -0 ~0" in msg
        assert "(watch cycle" not in msg

    def test_watch_cycle_footer(self) -> None:
        msg = generate_commit_message(
            rsid="rs_a",
            captured_at="2026-05-11T15:00:00Z",
            change_summary=None,
            watch_cycle=7,
        )
        assert msg.rstrip().endswith("(watch cycle 7)")

    def test_subject_truncated_at_72_chars_for_long_rsid(self) -> None:
        long_rsid = "rs_" + "x" * 200
        msg = generate_commit_message(
            rsid=long_rsid,
            captured_at="2026-05-11T15:00:00Z",
            change_summary=None,
        )
        subject = msg.splitlines()[0]
        assert len(subject) <= 72
        assert subject.endswith(("…", "..."))

    def test_subject_keeps_full_rsid_when_short_enough(self) -> None:
        msg = generate_commit_message(
            rsid="rs_short",
            captured_at="2026-05-11T15:00:00Z",
            change_summary=None,
        )
        subject = msg.splitlines()[0]
        assert "rs_short" in subject
        assert "…" not in subject
