"""scripts/check_version_sync.py — happy + mismatch."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "check_version_sync.py"
REPO_ROOT = Path(__file__).parent.parent


def _run(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_version_sync_happy_path() -> None:
    """Against the real repo at HEAD, check_version_sync should pass."""
    result = _run(REPO_ROOT)
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"


def test_check_version_sync_detects_mismatch(tmp_path: Path) -> None:
    """Synthetic fixture with a version drift between version.py and CHANGELOG.md."""
    src = tmp_path / "src" / "aa_auto_sdr" / "core"
    src.mkdir(parents=True)
    (src / "version.py").write_text('__version__ = "9.9.9"\n')
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "aa-auto-sdr"\ndynamic = ["version"]\n'
        '[tool.hatch.version]\npath = "src/aa_auto_sdr/core/version.py"\n'
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [0.0.1] — 2026-04-26\n\nOld stuff.\n")
    (tmp_path / "README.md").write_text("> **Status:** v0.0\n")
    result = _run(tmp_path)
    assert result.returncode != 0
    err = result.stdout + result.stderr
    assert "9.9.9" in err or "0.0.1" in err
