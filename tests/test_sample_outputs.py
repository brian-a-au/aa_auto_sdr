"""Asserts sample_outputs/ matches what scripts/build_sample_outputs.py produces.

Re-runs the build script in a tmp_path and byte-diffs every generated file
against the committed tree. CI fails if a code change drifted the samples
without a regenerate.

xlsx is excluded from the byte-check because xlsxwriter embeds the current
time in zip metadata (not deterministic across runs). All other formats are
byte-stable and checked."""

from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
SCRIPT_REL = Path("scripts") / "build_sample_outputs.py"
COMMITTED = REPO / "sample_outputs"

# xlsx isn't byte-deterministic (xlsxwriter creation-time in zip metadata).
_NON_DETERMINISTIC_SUFFIXES = (".xlsx",)


def _is_byte_checked(name: str) -> bool:
    return not any(name.endswith(suf) for suf in _NON_DETERMINISTIC_SUFFIXES)


def test_sample_outputs_up_to_date(tmp_path: Path) -> None:
    """Run the script in a tmp clone of the repo, then byte-diff sample_outputs/."""
    work = tmp_path / "repo"
    work.mkdir()
    for sub in ("scripts", "src", "tests/fixtures"):
        target = work / sub
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(REPO / sub, target)

    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    result = subprocess.run(
        [sys.executable, str(work / SCRIPT_REL)],
        cwd=work,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, f"build script failed: {result.stderr}"

    fresh = work / "sample_outputs"
    diff = filecmp.dircmp(fresh, COMMITTED)
    assert not diff.left_only, f"new files not committed: {diff.left_only}"
    assert not diff.right_only, f"committed files not in fresh build: {diff.right_only}"

    byte_checked = [f for f in diff.common_files if _is_byte_checked(f)]
    _, mismatches, errors = filecmp.cmpfiles(fresh, COMMITTED, byte_checked, shallow=False)
    assert not mismatches, (
        f"sample_outputs/ drift: {mismatches}. "
        "Run `uv run python scripts/build_sample_outputs.py` and commit."
    )
    assert not errors, f"diff errors: {errors}"
